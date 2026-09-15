package plugin

import (
	"context"
	"errors"
	"testing"
)

type rec struct {
	NoOp
	name  string
	log   *[]string
	sc    bool
	fail  bool
}

func (r rec) Name() string { return r.name }
func (r rec) PreHook(_ context.Context, q *Request) (*Request, *ShortCircuit, error) {
	*r.log = append(*r.log, "pre:"+r.name)
	if r.fail {
		return nil, nil, errors.New("boom")
	}
	if r.sc {
		return q, &ShortCircuit{Response: &Response{Status: 200, Body: []byte("cached")}}, nil
	}
	return q, nil, nil
}
func (r rec) PostHook(_ context.Context, _ *Request, p *Response) (*Response, error) {
	*r.log = append(*r.log, "post:"+r.name)
	return p, nil
}

func provider(log *[]string) func(context.Context, *Request) *Response {
	return func(context.Context, *Request) *Response {
		*log = append(*log, "provider")
		return &Response{Status: 200, Body: []byte("live")}
	}
}

func TestOrderAndReversePost(t *testing.T) {
	var log []string
	c := NewChain(rec{name: "a", log: &log}, rec{name: "b", log: &log})
	r := c.Run(context.Background(), &Request{}, provider(&log))
	want := []string{"pre:a", "pre:b", "provider", "post:b", "post:a"}
	if string(r.Body) != "live" || !eq(log, want) {
		t.Fatalf("got %v", log)
	}
}

func TestShortCircuitSkipsProviderAndLaterPlugins(t *testing.T) {
	var log []string
	c := NewChain(rec{name: "ledger", log: &log}, rec{name: "cache", log: &log, sc: true}, rec{name: "never", log: &log})
	r := c.Run(context.Background(), &Request{}, provider(&log))
	want := []string{"pre:ledger", "pre:cache", "post:cache", "post:ledger"}
	if string(r.Body) != "cached" || !eq(log, want) || r.Headers["X-Plugin-Short-Circuit"] != "cache" {
		t.Fatalf("got %v %q %v", log, r.Body, r.Headers)
	}
}

func TestPluginErrorIsIsolated(t *testing.T) {
	var log []string
	c := NewChain(rec{name: "bad", log: &log, fail: true}, rec{name: "ok", log: &log})
	c.logf = func(string, ...any) {}
	r := c.Run(context.Background(), &Request{}, provider(&log))
	want := []string{"pre:bad", "pre:ok", "provider", "post:ok"} // bad's PostHook must NOT run
	if string(r.Body) != "live" || !eq(log, want) {
		t.Fatalf("got %v", log)
	}
}

func eq(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
