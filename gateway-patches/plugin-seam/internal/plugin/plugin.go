// Package plugin is the freebuff-unified plugin seam — a deliberately small
// subset of Bifrost's LLMPlugin contract (core/schemas/plugin.go, Apache-2.0)
// adapted to the fiber v3 handlers in internal/httpapi.
//
// Why: eval harness, spend ledger and semantic cache are all "look at the
// request, maybe short-circuit, look at the response" — one seam instead of
// three more code paths in server.go.
//
// Contract (mirrors Bifrost):
//   - PreHook may rewrite the request or return a ShortCircuit (skip provider).
//   - PostHooks run in REVERSE order, and only for plugins whose PreHook ran.
//   - A plugin error is logged, never fatal: the request proceeds as if the
//     plugin were absent (Bifrost: "plugins must not take the gateway down").
//   - AllowFallbacks nil ⇒ true.
package plugin

import (
	"context"
	"log"
	"sync"
	"time"
)

// Request is the provider-neutral view of a chat call. Body is the raw JSON
// so passthrough stays byte-exact; the parsed fields are for policy decisions.
type Request struct {
	Path        string            // /v1/chat/completions | /v1/messages
	Headers     map[string]string // case-insensitive lookup via Header()
	Body        []byte
	Model       string
	Stream      bool
	Temperature float64
	HasTools    bool
	Messages    []Message
	ClientKey   string // fbu_ virtual key (for per-key ledgers)
	Meta        map[string]any
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Response is what goes back to the client. Body raw; Usage parsed if present.
type Response struct {
	Status  int
	Headers map[string]string
	Body    []byte
	Usage   Usage
	Latency time.Duration
	Err     error // non-nil when the provider call failed
}

type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

// ShortCircuit lets a PreHook answer without calling a provider (cache hit,
// budget exceeded, guardrail block).
type ShortCircuit struct {
	Response       *Response
	AllowFallbacks *bool // nil == true
}

// Plugin is the seam. Keep it this small on purpose.
type Plugin interface {
	Name() string
	PreHook(ctx context.Context, req *Request) (*Request, *ShortCircuit, error)
	PostHook(ctx context.Context, req *Request, resp *Response) (*Response, error)
	Cleanup() error
}

// NoOp embeds a do-nothing implementation so plugins implement only what they need.
type NoOp struct{}

func (NoOp) PreHook(_ context.Context, r *Request) (*Request, *ShortCircuit, error) { return r, nil, nil }
func (NoOp) PostHook(_ context.Context, _ *Request, r *Response) (*Response, error) { return r, nil }
func (NoOp) Cleanup() error                                                             { return nil }

// Chain runs plugins in order. Safe for concurrent use.
type Chain struct {
	mu      sync.RWMutex
	plugins []Plugin
	logf    func(string, ...any)
}

func NewChain(ps ...Plugin) *Chain { return &Chain{plugins: ps, logf: log.Printf} }

func (c *Chain) Add(p Plugin) { c.mu.Lock(); c.plugins = append(c.plugins, p); c.mu.Unlock() }

// Names is for /plugins/status.
func (c *Chain) Names() []string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	out := make([]string, len(c.plugins))
	for i, p := range c.plugins {
		out[i] = p.Name()
	}
	return out
}

// Run executes pre → call → post with Bifrost semantics.
// `call` is the real provider invocation; it is skipped on short-circuit.
func (c *Chain) Run(ctx context.Context, req *Request, call func(context.Context, *Request) *Response) *Response {
	c.mu.RLock()
	ps := append([]Plugin(nil), c.plugins...)
	c.mu.RUnlock()

	ran := make([]Plugin, 0, len(ps))
	var resp *Response
	for _, p := range ps {
		nr, sc, err := p.PreHook(ctx, req)
		if err != nil {
			c.logf("plugin %s PreHook: %v (ignored)", p.Name(), err)
			continue // plugin failure ≠ request failure
		}
		ran = append(ran, p)
		if nr != nil {
			req = nr
		}
		if sc != nil && sc.Response != nil {
			resp = sc.Response
			if resp.Headers == nil {
				resp.Headers = map[string]string{}
			}
			resp.Headers["X-Plugin-Short-Circuit"] = p.Name()
			break
		}
	}
	if resp == nil {
		t0 := time.Now()
		resp = call(ctx, req)
		if resp != nil {
			resp.Latency = time.Since(t0)
		}
	}
	for i := len(ran) - 1; i >= 0; i-- { // reverse order, only those that ran
		nr, err := ran[i].PostHook(ctx, req, resp)
		if err != nil {
			c.logf("plugin %s PostHook: %v (ignored)", ran[i].Name(), err)
			continue
		}
		if nr != nil {
			resp = nr
		}
	}
	return resp
}

// Close calls Cleanup on every plugin; first error wins but all run.
func (c *Chain) Close() error {
	c.mu.RLock()
	defer c.mu.RUnlock()
	var first error
	for _, p := range c.plugins {
		if err := p.Cleanup(); err != nil && first == nil {
			first = err
		}
	}
	return first
}
