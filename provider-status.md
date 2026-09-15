# AI Stack — Provider & Infrastructure Status

**Generated:** 2026-09-15T00:00:00Z  
**Source:** `scripts/gen-status.py` (`status/providers.yaml`)  
**Do not edit by hand** — edit `status/providers.yaml` and re-run the generator.

## Truth table

| Kind | Name | State | Detail | Last verified | Source |
|---|---|---|---|---|---|
| provider | **Cloudflare Workers AI** | ✅ LIVE | llama-3.1-8b-fast/fp8, llama-3.2-1b/3b, llama-4-scout, mistral-small-3.1 (llama-3.1-8b-instruct deprecated 2026-05-30) | `2026-09-04T00:00:00Z` | manual |
| provider | **OpenRouter** | ✅ LIVE | llama-3.1-8b-instruct confirmed, 359+ models | `2026-09-04T00:00:00Z` | manual |
| provider | **Fireworks** | ✅ LIVE | deepseek-v4-flash confirmed, 19 models | `2026-09-04T00:00:00Z` | manual |
| provider | **Google Gemini** | ✅ LIVE | gemini-2.5-flash confirmed, 3 verified keys (key 5 transient 503, key 7 empty) | `2026-09-04T00:00:00Z` | manual |
| provider | **Cohere** | ✅ LIVE | command-a-03-2025 confirmed, 8+ models | `2026-09-04T00:00:00Z` | manual |
| provider | **Ollama (local)** | ✅ LIVE | qwen2.5:3b, gemma4:e2b, deepseek-r1:1.5b, nomic-embed-text | `2026-09-04T00:00:00Z` | manual |
| provider | **Groq** | ❌ BLOCKED | CONFLICT RESOLVED — v3.7 said 16 models live, v3.7.2 said all keys 404; later report wins. Re-verify. | `2026-09-04T00:00:00Z` | manual |
| provider | **Together** | ⚠️ WALLET-GATED | key valid, "Credit limit exceeded" | `2026-09-04T00:00:00Z` | manual |
| provider | **DeepSeek** | ⚠️ WALLET-GATED | 4 keys valid, $0.00 balance | `2026-09-04T00:00:00Z` | manual |
| provider | **Cerebras** | ⚠️ WALLET-GATED | key valid, empty wallet | `2026-09-04T00:00:00Z` | manual |
| provider | **OpenAI** | ⚠️ WALLET-GATED | sk-proj key valid, no credits (429) | `2026-09-04T00:00:00Z` | manual |
| provider | **Venice** | ⚠️ WALLET-GATED | key valid, empty wallet | `2026-09-04T00:00:00Z` | manual |
| provider | **xAI / Grok** | ⚠️ WALLET-GATED | key valid, team has no credits (permission denied) | `2026-09-04T00:00:00Z` | manual |
| provider | **ZenMux** | ⚠️ WALLET-GATED | key valid, 402 no credit | `2026-09-04T00:00:00Z` | manual |
| provider | **MiniMax** | ❌ BLOCKED | 1008 account blocked | `2026-09-04T00:00:00Z` | manual |
| provider | **Moonshot** | ❌ BLOCKED | account blocked | `2026-09-04T00:00:00Z` | manual |
| provider | **NVIDIA** | ❌ BLOCKED | all slugs 404/410 Gone, catalog dead — stop probing | `2026-09-04T00:00:00Z` | manual |
| provider | **Mistral** | ❌ BLOCKED | 5th consecutive 429, not recovering — stop probing | `2026-09-04T00:00:00Z` | manual |
| provider | **SiliconFlow** | ❌ BLOCKED | invalid key | `2026-09-04T00:00:00Z` | manual |
| provider | **Morph / BrowseAI / CLIAgents / BrowserUse** | ❌ BLOCKED | empty responses | `2026-09-04T00:00:00Z` | manual |
| provider | **Bright Data** | ❌ BLOCKED | wrong endpoint | `2026-09-04T00:00:00Z` | manual |
| provider | **ElevenLabs** | ❌ BLOCKED | 0 voices | `2026-09-04T00:00:00Z` | manual |
| infra | **freebuff-unified gateway :18080** | ✅ LIVE | systemd active | `2026-09-04T00:00:00Z` | manual |
| infra | **hermes sidecar :3101** | ✅ LIVE | TLS 1.3 / HTTP2 stealth fetch | `2026-09-04T00:00:00Z` | manual |
| infra | **lmarena sidecar :3103** | ✅ LIVE | arena sessions + eval relay | `2026-09-04T00:00:00Z` | manual |
| infra | **owl-agent :60000** | ✅ LIVE | proxy defense, chameleon fingerprints, MCP fetch | `2026-09-04T00:00:00Z` | manual |
| infra | **owl metrics :9101** | ✅ LIVE | Prometheus, 55 proxies | `2026-09-04T00:00:00Z` | manual |
| infra | **AutoClaw proxy :31000** | ⚠️ WALLET-GATED | active, 6 models, 0 accounts (needs Z.ai email:password batch login) | `2026-09-04T00:00:00Z` | manual |
| infra | **GitHub Pages** | ✅ LIVE | marktantongco.github.io/ai-stack — build status "built" | `2026-09-15T00:00:00Z` | manual |
| infra | **Vercel** | ⚠️ WALLET-GATED | 302 SSO-gated — disable Deployment Protection for a public URL | `2026-09-04T00:00:00Z` | manual |
| infra | **Rust stealth proxy :443** | ❔ UNKNOWN | binary built, stealth-tested; not launched (needs domain + ACME email) | `2026-09-04T00:00:00Z` | manual |
| infra | **Token cloud** | ✅ LIVE | v3.7, 143 keys, chmod 600 | `2026-09-04T00:00:00Z` | manual |
| infra | **GitLab** | ✅ LIVE | 20 projects | `2026-09-04T00:00:00Z` | manual |
| infra | **Webshare proxies** | ✅ LIVE | 2/2 tested 200 | `2026-09-04T00:00:00Z` | manual |

## Summary

| State | Count |
|---|---|
| ✅ LIVE | 15 |
| ⚠️ WALLET-GATED | 9 |
| ❌ BLOCKED | 9 |
| ❔ UNKNOWN | 1 |

Rows whose **Source** is `gateway /health/all` are refreshed on every run; the rest are curated facts (wallet balances, account blocks) that no probe can see.
