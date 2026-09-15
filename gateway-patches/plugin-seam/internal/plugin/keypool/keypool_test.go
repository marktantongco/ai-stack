package keypool

import (
	"context"
	"testing"
	"time"

	"freebuff-unified/internal/plugin"
)

func newPool(t *testing.T, now *time.Time) *Pool {
	t.Helper()
	return New(Options{
		ProviderKeys: map[string][]string{"mistral": {"sk-mistral-aaaaaa", "sk-mistral-bbbbbb", "sk-mistral-cccccc"}},
		BaseCooldown: 10 * time.Second, MaxCooldown: time.Minute, DeadCooldown: time.Hour,
		Now: func() time.Time { return *now },
	})
}

func req() *plugin.Request { return &plugin.Request{Model: "mistral/mistral-small"} }

func used(r *plugin.Request) string { return r.Meta["upstream_key"].(string) }

func TestLRURotation(t *testing.T) {
	now := time.Unix(1000, 0)
	p := newPool(t, &now)
	seen := map[string]int{}
	for i := 0; i < 6; i++ {
		now = now.Add(time.Second)
		r, sc, _ := p.PreHook(context.Background(), req())
		if sc != nil {
			t.Fatal("unexpected short-circuit")
		}
		seen[used(r)]++
		p.PostHook(context.Background(), r, &plugin.Response{Status: 200})
	}
	for k, n := range seen {
		if n != 2 {
			t.Fatalf("key %s used %d times, want even spread", k, n)
		}
	}
}

func Test429CoolsOnlyThatKey(t *testing.T) {
	now := time.Unix(1000, 0)
	p := newPool(t, &now)
	r, _, _ := p.PreHook(context.Background(), req())
	bad := used(r)
	p.PostHook(context.Background(), r, &plugin.Response{Status: 429, Headers: map[string]string{"Retry-After": "30"}})
	for i := 0; i < 4; i++ {
		now = now.Add(time.Second)
		r2, sc, _ := p.PreHook(context.Background(), req())
		if sc != nil || used(r2) == bad {
			t.Fatalf("cooling key %s was reused (sc=%v)", bad, sc != nil)
		}
		p.PostHook(context.Background(), r2, &plugin.Response{Status: 200})
	}
	now = now.Add(31 * time.Second)
	st := p.Status()[0]
	if st.Healthy != 3 || st.State != "live" {
		t.Fatalf("key should be healthy after Retry-After: %+v", st)
	}
}

func TestExhaustedShortCircuitsWith429AndRetryAfter(t *testing.T) {
	now := time.Unix(1000, 0)
	p := newPool(t, &now)
	for i := 0; i < 3; i++ {
		r, _, _ := p.PreHook(context.Background(), req())
		p.PostHook(context.Background(), r, &plugin.Response{Status: 429})
	}
	_, sc, _ := p.PreHook(context.Background(), req())
	if sc == nil || sc.Response.Status != 429 || sc.Response.Headers["Retry-After"] == "" {
		t.Fatalf("want honest 429 short-circuit, got %+v", sc)
	}
	if sc.AllowFallbacks == nil || !*sc.AllowFallbacks {
		t.Fatal("exhausted pool must allow provider fallback")
	}
	if p.Status()[0].State != "exhausted" {
		t.Fatalf("state=%s", p.Status()[0].State)
	}
}

func TestBackoffDoublesAndCaps(t *testing.T) {
	now := time.Unix(1000, 0)
	p := New(Options{ProviderKeys: map[string][]string{"x": {"only-key-000000"}},
		BaseCooldown: 10 * time.Second, MaxCooldown: 25 * time.Second, Now: func() time.Time { return now }})
	want := []int{10, 20, 25, 25}
	for i, w := range want {
		r, _, _ := p.PreHook(context.Background(), &plugin.Request{Model: "x/m"})
		p.PostHook(context.Background(), r, &plugin.Response{Status: 429})
		if got := p.Status()[0].Keys[0].CoolingS; got != w {
			t.Fatalf("strike %d: cooling %ds want %ds", i+1, got, w)
		}
		now = now.Add(time.Duration(w) * time.Second)
	}
}

func TestWalletCodesParkKeyLong(t *testing.T) {
	now := time.Unix(1000, 0)
	p := New(Options{ProviderKeys: map[string][]string{"deepseek": {"k1-000000", "k2-000000"}},
		DeadCooldown: time.Hour, Now: func() time.Time { return now }})
	for i := 0; i < 2; i++ {
		r, _, _ := p.PreHook(context.Background(), &plugin.Request{Model: "deepseek/chat"})
		p.PostHook(context.Background(), r, &plugin.Response{Status: 402})
	}
	st := p.Status()[0]
	if st.State != "wallet" || st.Keys[0].CoolingS < 3500 {
		t.Fatalf("402 must park for DeadCooldown and report wallet: %+v", st)
	}
}

func TestUnknownProviderUntouched(t *testing.T) {
	now := time.Unix(1000, 0)
	p := newPool(t, &now)
	r, sc, err := p.PreHook(context.Background(), &plugin.Request{Model: "ollama/qwen2.5:3b"})
	if sc != nil || err != nil || r.Meta != nil {
		t.Fatal("providers without a pool must pass through")
	}
}

func TestSecretsNeverInStatus(t *testing.T) {
	now := time.Unix(1000, 0)
	p := newPool(t, &now)
	for _, k := range p.Status()[0].Keys {
		if len(k.ID) > 8 || k.ID == "sk-mistral-aaaaaa" {
			t.Fatalf("status leaks secret-ish id %q", k.ID)
		}
	}
}
