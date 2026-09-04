# AI Stack — Local AI Agent Infrastructure: Stealth Proxy, GLM Gateway & Token Cloud

> A self-hosted, privacy-first AI agent stack: stealth HTTPS proxying, an OpenAI-compatible GLM gateway with rotating proxies, centralized multi-provider token management, and opencode integration. Runs on Linux. No vendor lock-in.

**Keywords:** local AI stack, self-hosted LLM gateway, stealth proxy, GLM, open-source AI agents, opencode, OpenAI-compatible proxy, token management, Rust proxy, web scraping infrastructure.

## Architecture

```text
                    ┌─────────────────────────────┐
                    │        opencode CLI         │
                    │  autoclaw/glm-5.2 · turbo   │
                    └──────────────┬──────────────┘
                                   │ http://localhost:31000/v1
                    ┌──────────────▼──────────────┐
                    │  AutoClaw Proxy (:31000)    │  OpenAI-compatible GLM/Z.ai
                    │  systemd · auto-restart     │  gateway, rotating Webshare
                    └──────────────┬──────────────┘  proxies, dashboard UI
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼─────────┐   ┌──────────▼──────────┐   ┌─────────▼─────────┐
│ Freebuff :18080   │   │ Rust https_proxy    │   │ Token Cloud       │
│ AI gateway,       │   │ Let's Encrypt TLS,  │   │ 140+ keys: Gemini,│
│ circuit breaker,  │   │ nginx camouflage,   │   │ DeepSeek, Open-   │
│ rate limiter,     │   │ CONNECT tunneling   │   │ Router, Groq…     │
│ 9 US proxies      │   │                     │   │                   │
└───────────────────┘   └─────────────────────┘   └───────────────────┘
```

## Services

| Service | Address | Status | Notes |
|---|---|---|---|
| Freebuff gateway | `http://localhost:18080` | systemd, active | `/healthz`, `/v1/models`, `/v1/chat/completions`, `/proxy/verify` |
| AutoClaw proxy | `http://localhost:31000` | systemd, active | `/health`, `/v1/models`, `/v1/chat/completions`, dashboard UI |
| Stealth proxy (Rust) | `:443` (with domain) | binary built | Auto-ACME TLS, fake-nginx 404, multi-user auth |
| opencode provider | `autoclaw/glm-5.2`, `autoclaw/glm-5-turbo` | configured | Free GLM inference once logged in |

## Quickstart

```bash
# 1. AutoClaw proxy (needs accounts.txt with email:password lines)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp proxies.txt.example proxies.txt   # add host:port:user:pass lines
sudo systemctl enable --now autoclaw-proxy.service

# 2. Batch login (headless, rotating proxies dodge the Z.ai rate limit)
.venv/bin/python autoclaw_autologin.py --batch accounts.txt --headless --concurrent 3

# 3. Use free GLM inside opencode (provider preconfigured)
opencode run --model autoclaw/glm-5-turbo "hello"

# 4. Rust stealth proxy (needs a domain pointed at this host)
cp config.example.yaml config.yaml   # set domain + users
./target/release/https_proxy run --config config.yaml
```

## Components

- **autoclaw-autologin** — OpenAI-compatible reverse proxy + Google OAuth auto-login for AutoGLM/Z.ai, CloakBrowser stealth Chromium, token auto-refresh, wallet monitoring.
- **https_proxy** — Stealth HTTPS forward proxy in Rust: automatic Let's Encrypt certificates, HTTP/2 CONNECT, multi-user basic auth, nginx-404 camouflage for scanners.
- **secret-agent / @ulixee/hero** — Nearly-unblockable headless scraping browser (use the maintained `@ulixee/hero` package).
- **Token cloud** — Centralized, permission-locked (`chmod 600`) store for all provider keys, each live-validated against its correct endpoint.

## Security notes

- No credentials are stored in this repo. Token stores live outside version control with `600` permissions.
- Proxy credential files (`proxies.txt`, `tokens.json`, `accounts.txt`) are gitignored upstream — keep it that way.
- Operate automation within the terms of service of the providers you use.

## License

MIT — see component repos for their respective licenses.
