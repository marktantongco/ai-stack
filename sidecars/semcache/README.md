# semcache sidecar (:18090)

Semantic response cache (Bifrost/LiteLLM class) in front of the gateway. Zero deps.

```
systemctl --user enable --now sidecars/semcache/semcache.service   # or: python3 semcache.py
curl :18090/semcache/stats     # hit_rate, upstream_requests_avoided, embedder_available
curl :18090/metrics            # Prometheus
curl -X DELETE :18090/semcache/purge
```

Point opencode's `baseURL` at `http://127.0.0.1:18090/v1` instead of `:18080`.
Every response carries `X-Semcache: hit:exact | hit:semantic;score=… | miss;stored | bypass:<why>`.

Policy: exact key = model + normalized messages; semantic = cosine(nomic-embed-text) ≥ 0.95
on `system + last user turn`, same model family only; bypass when stream / tools /
temperature > 0.3 / n > 1; never caches non-200. Ollama down ⇒ exact-only mode, still serves.

Tests: `python3 -m unittest discover -s sidecars/semcache/tests` (fake gateway + fake embedder).
