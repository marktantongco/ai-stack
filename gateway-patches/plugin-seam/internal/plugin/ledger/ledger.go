// Package ledger is the first real plugin on the seam: a per-key, per-model
// spend/usage ledger (LiteLLM SpendLogs class) with an optional budget gate.
//
// It closes the "wallet-gated is hand-maintained" gap: gen-status.py can read
// /plugins/ledger/summary and compute `wallet` state instead of a human
// editing providers.yaml. Storage is a JSONL file (append-only, no DB dep);
// swap for SQLite when rows > ~1M.
package ledger

import (
	"bufio"
	"context"
	"encoding/json"
	"os"
	"strings"
	"sync"
	"time"

	"freebuff-unified/internal/plugin" // adjust to the gateway module path
)

// Price is USD per 1M tokens. Free-tier providers are 0/0 but we still count
// tokens — the 429 budget is in tokens, not dollars.
type Price struct{ In, Out float64 }

type Row struct {
	TS        time.Time `json:"ts"`
	Key       string    `json:"key"`
	Model     string    `json:"model"`
	Prompt    int       `json:"prompt_tokens"`
	Compl     int       `json:"completion_tokens"`
	USD       float64   `json:"usd"`
	LatencyMS int64     `json:"latency_ms"`
	Status    int       `json:"status"`
	Short     string    `json:"short_circuit,omitempty"`
}

type Ledger struct {
	plugin.NoOp
	mu      sync.Mutex
	w       *bufio.Writer
	f       *os.File
	prices  map[string]Price // prefix match on model
	budget  map[string]float64 // key -> USD/day; 0 = unlimited
	spent   map[string]float64 // key -> USD today
	day     string
	totals  map[string]*Row // key|model -> aggregate
}

func New(path string, prices map[string]Price, budget map[string]float64) (*Ledger, error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, err
	}
	return &Ledger{f: f, w: bufio.NewWriter(f), prices: prices, budget: budget,
		spent: map[string]float64{}, totals: map[string]*Row{}, day: today()}, nil
}

func (l *Ledger) Name() string { return "ledger" }

// PreHook: budget gate. Short-circuits with 402 when a key is over its daily USD budget.
func (l *Ledger) PreHook(_ context.Context, r *plugin.Request) (*plugin.Request, *plugin.ShortCircuit, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.rollDay()
	if b := l.budget[r.ClientKey]; b > 0 && l.spent[r.ClientKey] >= b {
		no := false
		body, _ := json.Marshal(map[string]any{"error": map[string]any{
			"type": "budget_exceeded", "message": "daily budget exhausted for this key",
			"spent_usd": l.spent[r.ClientKey], "budget_usd": b}})
		return r, &plugin.ShortCircuit{AllowFallbacks: &no,
			Response: &plugin.Response{Status: 402, Body: body,
				Headers: map[string]string{"Content-Type": "application/json"}}}, nil
	}
	return r, nil, nil
}

// PostHook: record usage. Runs for short-circuited responses too (cache hits
// cost 0 but we want to *see* them).
func (l *Ledger) PostHook(_ context.Context, r *plugin.Request, p *plugin.Response) (*plugin.Response, error) {
	if p == nil {
		return p, nil
	}
	pr := l.price(r.Model)
	usd := (float64(p.Usage.PromptTokens)*pr.In + float64(p.Usage.CompletionTokens)*pr.Out) / 1e6
	row := Row{TS: time.Now().UTC(), Key: r.ClientKey, Model: r.Model, Prompt: p.Usage.PromptTokens,
		Compl: p.Usage.CompletionTokens, USD: usd, LatencyMS: p.Latency.Milliseconds(), Status: p.Status,
		Short: p.Headers["X-Plugin-Short-Circuit"]}
	l.mu.Lock()
	defer l.mu.Unlock()
	l.rollDay()
	l.spent[r.ClientKey] += usd
	k := r.ClientKey + "|" + r.Model
	t := l.totals[k]
	if t == nil {
		t = &Row{Key: r.ClientKey, Model: r.Model}
		l.totals[k] = t
	}
	t.Prompt += row.Prompt
	t.Compl += row.Compl
	t.USD += usd
	b, _ := json.Marshal(row)
	l.w.Write(b)
	l.w.WriteByte('\n')
	return p, nil
}

// Summary feeds /plugins/ledger/summary → gen-status.py.
func (l *Ledger) Summary() map[string]any {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.w.Flush()
	rows := make([]Row, 0, len(l.totals))
	for _, r := range l.totals {
		rows = append(rows, *r)
	}
	return map[string]any{"day": l.day, "spent_usd_by_key": l.spent, "totals": rows}
}

func (l *Ledger) Cleanup() error { l.mu.Lock(); defer l.mu.Unlock(); l.w.Flush(); return l.f.Close() }

func (l *Ledger) price(model string) Price {
	best, bestLen := Price{}, -1
	for prefix, p := range l.prices {
		if strings.HasPrefix(model, prefix) && len(prefix) > bestLen {
			best, bestLen = p, len(prefix)
		}
	}
	return best
}

func (l *Ledger) rollDay() {
	if d := today(); d != l.day {
		l.day, l.spent = d, map[string]float64{}
	}
}

func today() string { return time.Now().UTC().Format("2006-01-02") }
