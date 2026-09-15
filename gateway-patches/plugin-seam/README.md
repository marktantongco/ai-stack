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
| `keypool` | Reliability — rotate keys within a provider on 429/402 before demoting the provider | planned — needs `credentials` package access |

## Test

```
cd unified-freebuff-proxy && go test ./internal/plugin/...
```
