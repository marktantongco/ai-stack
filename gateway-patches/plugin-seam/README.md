# Plugin seam for freebuff-unified (Bifrost-class)

Drop-in for `marktantongco/unified-freebuff-proxy`. This directory mirrors the
gateway's tree; copy `internal/plugin/` across, then apply the 3 wiring edits below.
It is parked here because `ai-stack` is the umbrella repo and this sandbox has no
Go toolchain to build the gateway (egress to go.dev is blocked); the seam itself
is < 150 lines and its tests are table-driven.

## Contract (from Bifrost `core/schemas/plugin.go`, Apache-2.0)

| Bifrost | Here | Kept? |
|---|---|---|
| `PreLLMHook(ctx, req) (req, *ShortCircuit, err)` | `PreHook` | ✅ |
| `PostLLMHook(ctx, resp, err)` | `PostHook(ctx, req, resp)` | ✅ (+req, we need the key) |
| PostHooks run in **reverse**, only for plugins whose PreHook ran | same | ✅ tested |
| Plugin error is logged, never fatal | same | ✅ tested |
| `ShortCircuit.AllowFallbacks` nil ⇒ true | same | ✅ |
| `PreMCPHook`, `HTTPTransportPreHook`, WASM loading, `PluginStatus` | — | ❌ not yet — add when owl's MCP surface moves into the gateway |

## Wiring (3 edits in `internal/httpapi`)

1. **`server.go` `Options`** — add `Plugins *plugin.Chain`.
2. **`chat_service.go`** — where the provider is called today, wrap:

   ```go
   req := plugin.FromChatRequest(c, body, clientKey)          // small adapter, ~20 lines
   resp := h.plugins.Run(c.Context(), req, func(ctx context.Context, r *plugin.Request) *plugin.Response {
       return h.callProvider(ctx, r)                           // existing code, unchanged
   })
   return plugin.Write(c, resp)                                // status/headers/body
   ```
   Streaming requests skip the chain (`req.Stream` ⇒ `call` directly); Bifrost
   does the same for SSE until PostHook streaming lands.
3. **`server.go` routes** — `app.Get("/plugins/status", …)` returning `Plugins.Names()`,
   and per-plugin admin routes (e.g. `/plugins/ledger/summary`).

## First plugins on the seam

| Plugin | Gap row it closes | Status |
|---|---|---|
| `ledger` | FinOps — per-key/model tokens + USD, daily budget gate (402) | ✅ in this dir |
| `semcache` | Cost/latency — semantic cache | ✅ shipped as a **sidecar** (`sidecars/semcache/`) today; becomes a PreHook short-circuit once the seam is in |
| `eval` | move `lmarena_eval.go` sealed-store behind a PostHook | planned — pure refactor |
| `keypool` | Reliability — LRU key rotation per provider; 429 → cool that key (Retry-After or doubling backoff); 401/402/403 → park 6h; whole pool cooling → honest 429 + Retry-After with `AllowFallbacks=true` so the failover daemon can swap provider | ✅ in this dir, 7 tests |

## Wiring keypool to the token cloud

`ProviderKeys` is filled by the wiring code from `~/.env-tokens/` (chmod 600), grouped
by the model-id prefix (`groq/…`, `mistral/…`). The chosen secret lands in
`req.Meta["upstream_key"]`; the existing upstream client reads it from there instead
of the single `credentials.Store` credential. `/plugins/keypool/status` exposes
per-provider `live | degraded | exhausted | wallet` — `gen-status.py` can consume it
directly, replacing the hand-maintained wallet rows in `status/providers.yaml`.

## How to land this in unified-freebuff-proxy

The Arena sandbox has no push access to that repo (`permissions.push=false`) and no
Go toolchain (go.dev / dl.google.com / release-assets egress blocked), so this is a
patch bundle, not a PR:

```
cd unified-freebuff-proxy
cp -r ../ai-stack/gateway-patches/plugin-seam/internal/plugin internal/
go vet ./internal/plugin/... && go test -race ./internal/plugin/...
# then the 3 wiring edits above
```

Reviewed by hand for compile blockers (imports, brace balance, unused vars); the
first `go test` run there is the real acceptance step.

## Test

```
cd unified-freebuff-proxy && go test ./internal/plugin/...
```
