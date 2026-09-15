// Package keypool is the "Reliability" plugin: rotate keys *within* a provider
// on 429/401/402 before the failover daemon demotes the whole provider.
//
// Today the gateway has one credential + a breaker (auth.breaker: threshold 3,
// cooldown 12h). With 143 keys in the token cloud that means "Mistral: 5th
// consecutive 429 → permanently blocked" even when 4 other Mistral keys are
// idle. keypool turns that tombstone into a rotating pool:
//
//   PreHook   pick the healthiest key for req.Model's provider, put it in
//             req.Meta["upstream_key"] and X-Keypool-Key-Id (first 8 chars).
//   PostHook  429 → cool that key for Retry-After (or backoff); 401/402/403 →
//             park it for `dead_cooldown` (wallet/blocked, not transient);
//             2xx → reset backoff. If EVERY key is cooling, short-circuit 429
//             with the soonest Retry-After so the client (and failover daemon)
//             gets an honest signal instead of a 5th wasted upstream call.
//
// Selection is least-recently-used among healthy keys ⇒ even RPM spread per
// key, which is what free-tier limits actually meter.
//
// Keys come from ProviderKeys — read from the existing chmod-600 token cloud
// by the wiring code, never from config.yaml.
package keypool

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"freebuff-unified/internal/plugin" // adjust to the gateway module path
)

type Options struct {
	// ProviderKeys: provider name → API keys. Provider is the prefix of the
	// model id before the first "/" (opencode convention: "groq/llama-3.3-70b").
	ProviderKeys map[string][]string
	BaseCooldown time.Duration // 429 without Retry-After; doubles per strike, capped
	MaxCooldown  time.Duration
	DeadCooldown time.Duration // 401/402/403 — wallet empty / key revoked
	Now          func() time.Time
}

func (o *Options) defaults() {
	if o.BaseCooldown == 0 {
		o.BaseCooldown = 20 * time.Second
	}
	if o.MaxCooldown == 0 {
		o.MaxCooldown = 15 * time.Minute
	}
	if o.DeadCooldown == 0 {
		o.DeadCooldown = 6 * time.Hour
	}
	if o.Now == nil {
		o.Now = time.Now
	}
}

type key struct {
	secret   string
	id       string // first 8 chars of sha-less secret tail — safe to log
	until    time.Time
	strikes  int
	lastUsed time.Time
	ok, hit  int
	lastCode int
}

type Pool struct {
	plugin.NoOp
	o    Options
	mu   sync.Mutex
	pool map[string][]*key
}

func New(o Options) *Pool {
	o.defaults()
	p := &Pool{o: o, pool: map[string][]*key{}}
	for prov, secrets := range o.ProviderKeys {
		for _, s := range secrets {
			if s = strings.TrimSpace(s); s != "" {
				p.pool[prov] = append(p.pool[prov], &key{secret: s, id: keyID(s)})
			}
		}
	}
	return p
}

func (p *Pool) Name() string { return "keypool" }

func provider(model string) string {
	if i := strings.IndexByte(model, '/'); i > 0 {
		return strings.ToLower(model[:i])
	}
	return ""
}

func keyID(s string) string {
	if len(s) <= 8 {
		return "********"
	}
	return "…" + s[len(s)-6:]
}

// PreHook selects a key; providers without a pool are left untouched.
func (p *Pool) PreHook(_ context.Context, r *plugin.Request) (*plugin.Request, *plugin.ShortCircuit, error) {
	prov := provider(r.Model)
	p.mu.Lock()
	defer p.mu.Unlock()
	ks := p.pool[prov]
	if len(ks) == 0 {
		return r, nil, nil
	}
	now := p.o.Now()
	var pick *key
	soonest := time.Time{}
	for _, k := range ks {
		if k.until.After(now) {
			if soonest.IsZero() || k.until.Before(soonest) {
				soonest = k.until
			}
			continue
		}
		if pick == nil || k.lastUsed.Before(pick.lastUsed) { // LRU among healthy
			pick = k
		}
	}
	if pick == nil { // whole pool cooling → honest 429, no upstream call
		retry := int(soonest.Sub(now).Seconds()) + 1
		body, _ := json.Marshal(map[string]any{"error": map[string]any{
			"type": "rate_limit_error", "code": "keypool_exhausted",
			"message": fmt.Sprintf("all %d %s keys cooling; retry in %ds", len(ks), prov, retry)}})
		yes := true
		return r, &plugin.ShortCircuit{AllowFallbacks: &yes, Response: &plugin.Response{
			Status: 429, Body: body, Headers: map[string]string{
				"Content-Type": "application/json", "Retry-After": strconv.Itoa(retry),
				"X-Keypool": prov + ":exhausted"}}}, nil
	}
	pick.lastUsed = now
	if r.Meta == nil {
		r.Meta = map[string]any{}
	}
	r.Meta["upstream_key"] = pick.secret
	r.Meta["keypool_id"] = pick.id
	if r.Headers == nil {
		r.Headers = map[string]string{}
	}
	r.Headers["X-Keypool-Key-Id"] = pick.id
	return r, nil, nil
}

// PostHook applies the verdict to the key that was used.
func (p *Pool) PostHook(_ context.Context, r *plugin.Request, resp *plugin.Response) (*plugin.Response, error) {
	if resp == nil || r.Meta == nil {
		return resp, nil
	}
	secret, _ := r.Meta["upstream_key"].(string)
	if secret == "" {
		return resp, nil
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, k := range p.pool[provider(r.Model)] {
		if k.secret != secret {
			continue
		}
		k.lastCode = resp.Status
		now := p.o.Now()
		switch {
		case resp.Status == 429:
			k.strikes++
			k.hit++
			d := p.o.BaseCooldown << uint(k.strikes-1)
			if ra := retryAfter(resp.Headers); ra > 0 {
				d = ra
			}
			if d > p.o.MaxCooldown {
				d = p.o.MaxCooldown
			}
			k.until = now.Add(d)
		case resp.Status == 401 || resp.Status == 402 || resp.Status == 403:
			k.strikes++
			k.hit++
			k.until = now.Add(p.o.DeadCooldown)
		case resp.Status >= 200 && resp.Status < 300:
			k.strikes, k.until = 0, time.Time{}
			k.ok++
		}
		if resp.Headers == nil {
			resp.Headers = map[string]string{}
		}
		resp.Headers["X-Keypool-Key-Id"] = k.id
		break
	}
	return resp, nil
}

func retryAfter(h map[string]string) time.Duration {
	for k, v := range h {
		if strings.EqualFold(k, "Retry-After") {
			if n, err := strconv.Atoi(strings.TrimSpace(v)); err == nil && n > 0 {
				return time.Duration(n) * time.Second
			}
		}
	}
	return 0
}

// Status feeds /plugins/keypool/status and gen-status.py: per provider, how
// many keys are healthy vs cooling, and why. Secrets never leave this struct.
type KeyStatus struct {
	ID        string `json:"id"`
	Healthy   bool   `json:"healthy"`
	CoolingS  int    `json:"cooling_s,omitempty"`
	Strikes   int    `json:"strikes"`
	OK        int    `json:"ok"`
	Throttled int    `json:"throttled"`
	LastCode  int    `json:"last_code,omitempty"`
}

type ProviderStatus struct {
	Provider string      `json:"provider"`
	Healthy  int         `json:"healthy"`
	Total    int         `json:"total"`
	State    string      `json:"state"` // live | degraded | exhausted | wallet
	Keys     []KeyStatus `json:"keys"`
}

func (p *Pool) Status() []ProviderStatus {
	p.mu.Lock()
	defer p.mu.Unlock()
	now := p.o.Now()
	out := make([]ProviderStatus, 0, len(p.pool))
	for prov, ks := range p.pool {
		ps := ProviderStatus{Provider: prov, Total: len(ks)}
		allDead := len(ks) > 0
		for _, k := range ks {
			s := KeyStatus{ID: k.id, Healthy: !k.until.After(now), Strikes: k.strikes, OK: k.ok, Throttled: k.hit, LastCode: k.lastCode}
			if !s.Healthy {
				s.CoolingS = int(k.until.Sub(now).Seconds())
			} else {
				ps.Healthy++
			}
			if !(k.lastCode == 401 || k.lastCode == 402 || k.lastCode == 403) {
				allDead = false
			}
			ps.Keys = append(ps.Keys, s)
		}
		switch {
		case ps.Healthy == ps.Total:
			ps.State = "live"
		case ps.Healthy > 0:
			ps.State = "degraded"
		case allDead:
			ps.State = "wallet"
		default:
			ps.State = "exhausted"
		}
		out = append(out, ps)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Provider < out[j].Provider })
	return out
}
