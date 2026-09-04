# Freebuff AI Provider Status — Live Report

**Generated:** 2026-09-04 UTC  
**Token cloud:** v3.7, 143 keys  
**Infrastructure:** Both services active, Pages live

---

## ✅ Live Inference (Confirmed Working)

### 1. Cloudflare Workers AI (CFUT key verified)
| Model | Status |
|---|---|
| `@cf/meta/llama-3.1-8b-instruct-fast` | ✅ Inference OK |
| `@cf/meta/llama-3.1-8b-instruct-fp8` | ✅ 200 |
| `@cf/meta/llama-3.2-3b-instruct` | ✅ 200 |
| `@cf/meta/llama-3.2-1b-instruct` | ✅ 200 |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | ✅ 200 |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | ✅ Batch |
| `@cf/mistralai/mistral-small-3.1-24b-instruct` | ✅ 200 |
| `@cf/deepseek-ai/deepseek-v4-flash-0731` | ⚠️ 403 paid |
| `@cf/meta/llama-3.1-8b-instruct` | ❌ Deprecated 2026-05-30 |

### 2. OpenRouter
- `llama-3.1-8b-instruct` — ✅ Live inference confirmed
- 359+ models available

### 3. Fireworks
- `deepseek-v4-flash` — ✅ Live inference confirmed
- 19 models available

### 4. Google Gemini
- `gemini-2.5-flash` — ✅ Live inference confirmed
- 38+ models available
- 3 verified keys (key 5 = transient 503, key 7 = empty response)

### 5. Cohere
- `command-a-03-2025` — ✅ Live inference confirmed
- 8+ models available

### 6. Groq (Direct API)
- 16 models available, direct inference confirmed

### 7. Local Ollama
- `qwen2.5:3b` — ✅ Working
- `gemma4:e2b` — ✅ Working
- `deepseek-r1:1.5b` — ✅ Working
- `nomic-embed-text` — ✅ Working

---

## ⚠️ Valid Key, Wallet-Gated (Needs Credits)

| Provider | Key Status | Issue |
|---|---|---|
| Together | `tgp_v1_...` valid | "Credit limit exceeded" |
| DeepSeek | 4 keys, $0.00 | Empty wallet |
| Cerebras | Valid | Empty wallet |
| OpenAI | `sk-proj-oLDW...` | No credits |
| Venice | Valid | Empty wallet |
| MiniMax | 1008 | Account blocked |
| Moonshot | Blocked | Account blocked |
| xAI/Grok | Valid | Team has no credits |
| ZenMux | Valid | 402 no-credit |

---

## ❌ Permanently Blocked

| Provider | Reason |
|---|---|
| **NVIDIA** | All slugs 404/410 Gone, catalog dead |
| **Mistral** | 5th consecutive 429 rate limit, not recovering |

---

## 📊 Summary

| Category | Count |
|---|---|
| **Live inference providers** | **7** (Cloudflare, OpenRouter, Fireworks, Gemini, Cohere, Groq, Ollama) |
| **Valid but wallet-gated** | **9** |
| **Permanently blocked** | **2** (Mistral, NVIDIA) |
| Total keys in cloud | 143 |
| Active AutoClaw accounts | 0 |

---

## 🔧 Infrastructure Status

| Component | Status |
|---|---|
| `freebuff-unified` | ✅ Active `:18080`, 27h+ uptime |
| `autoclaw-proxy` | ✅ Active `:31000`, 0 accounts |
| GitHub Pages | ✅ 200 |
| Vercel | ⚠️ 302 (SSO gated) |
| Rust proxy | ✅ Built, stealth-tested |
| Token cloud | ✅ v3.7, 428 lines |
| Cloudflare model rename | ✅ Fixed (deprecated → fast/fp8 variants) |

---

## 📝 Remaining Action Items

### Immediate (paste-and-go)
1. **GLM-5.2 in opencode** — paste `email:password` → AutoClaw batch login
2. **Paid gateway** — paste 2 real tokens → swap into Freebuff config
3. **Public Rust proxy** — give domain + admin email → ACME + 443 launch

### Wallet top-ups
4. **Together** — add credits (key works, just empty)
5. **DeepSeek ×4** — add credits
6. **Cerebras / OpenAI / Venice / xAI / ZenMux** — add credits

### Configuration
7. **Vercel** — disable Deployment Protection → public URL
8. **Cloudflare** — replace `@cf/meta/llama-3.1-8b-instruct` with `@cf/meta/llama-3.1-8b-instruct-fast` in any configs
9. **NVIDIA** — mark permanently blocked, stop probing
10. **Mistral** — mark permanently blocked, stop probing

---

*This document is auto-generated. Run `curl localhost:18080/healthz` and `curl localhost:31000/health` for real-time status.*
