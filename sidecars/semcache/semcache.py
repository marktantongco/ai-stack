#!/usr/bin/env python3
"""semcache — semantic response cache sidecar for the freebuff gateway.

Sits in front of :18080 like the other sidecars. OpenAI-compatible clients
point at :18090 instead; everything that is not a cacheable chat completion is
relayed byte-for-byte (same passthrough contract as the gateway's /v1/*).

    client → :18090 semcache → :18080 freebuff-unified → providers
                     │
                     └── :11434 ollama /api/embeddings  (nomic-embed-text)

Cache policy (Bifrost/LiteLLM "semantic caching" class, minimum viable):
  1. exact-hit   sha256(model + normalized messages) → return stored body      (~0 ms)
  2. semantic    cosine(embed(last user turn + system), stored) ≥ THRESHOLD    (~30 ms)
                 same model family only, temperature ≤ 0.3, no tools, no stream
  3. miss        relay upstream, store response + vector, tag X-Semcache: miss

Why this exists: the free tier (Cloudflare/Groq/Mistral…) blocks on 429 long
before it blocks on money. Every hit is a request that never reaches a
rate-limited provider. Hits are reported in /semcache/stats and Prometheus at
/metrics so the failover daemon and gen-status.py can see them.

Zero third-party deps: stdlib http.server + urllib + sqlite3 + json.
Env:
  SEMCACHE_PORT=18090   SEMCACHE_UPSTREAM=http://127.0.0.1:18080
  SEMCACHE_OLLAMA=http://127.0.0.1:11434  SEMCACHE_EMBED_MODEL=nomic-embed-text
  SEMCACHE_THRESHOLD=0.95  SEMCACHE_TTL=86400  SEMCACHE_DB=~/.local/share/semcache/cache.db
  SEMCACHE_MAX_TEMP=0.3
"""
from __future__ import annotations

import hashlib
import http.server
import json
import math
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request

# ----------------------------------------------------------------------------- config
PORT = int(os.environ.get("SEMCACHE_PORT", "18090"))
UPSTREAM = os.environ.get("SEMCACHE_UPSTREAM", "http://127.0.0.1:18080").rstrip("/")
OLLAMA = os.environ.get("SEMCACHE_OLLAMA", "http://127.0.0.1:11434").rstrip("/")
EMBED_MODEL = os.environ.get("SEMCACHE_EMBED_MODEL", "nomic-embed-text")
THRESHOLD = float(os.environ.get("SEMCACHE_THRESHOLD", "0.95"))
TTL = int(os.environ.get("SEMCACHE_TTL", str(24 * 3600)))
MAX_TEMP = float(os.environ.get("SEMCACHE_MAX_TEMP", "0.3"))
DB_PATH = os.path.expanduser(os.environ.get("SEMCACHE_DB", "~/.local/share/semcache/cache.db"))
CACHEABLE_PATHS = {"/v1/chat/completions", "/v1/messages"}
HOP_HEADERS = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
               "proxy-authorization", "proxy-authenticate", "content-length", "host"}


# ----------------------------------------------------------------------------- store
class Store:
    """SQLite-backed store. Vectors are JSON arrays; brute-force cosine scan is fine
    for the tens-of-thousands of rows a single workstation produces (768-d × 50k ≈ 40 ms)."""

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True) if path != ":memory:" else None
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS entries(
              key TEXT PRIMARY KEY, family TEXT, vec TEXT, body BLOB,
              status INT, ctype TEXT, created REAL, hits INT DEFAULT 0);
            CREATE INDEX IF NOT EXISTS ix_family ON entries(family, created);
        """)
        self._vecs: dict[str, tuple[str, list[float]]] = {}  # key -> (family, vec) hot cache
        for k, fam, v in self.db.execute("SELECT key,family,vec FROM entries WHERE vec IS NOT NULL"):
            self._vecs[k] = (fam, json.loads(v))

    def get_exact(self, key: str) -> tuple[int, str, bytes] | None:
        with self.lock:
            row = self.db.execute(
                "SELECT status,ctype,body,created FROM entries WHERE key=?", (key,)).fetchone()
            if not row or time.time() - row[3] > TTL:
                return None
            self.db.execute("UPDATE entries SET hits=hits+1 WHERE key=?", (key,))
            return row[0], row[1], row[2]

    def nearest(self, family: str, vec: list[float]) -> tuple[float, str] | None:
        best, best_key = -1.0, None
        with self.lock:
            for k, (fam, v) in self._vecs.items():
                if fam != family:
                    continue
                s = cosine(vec, v)
                if s > best:
                    best, best_key = s, k
        return (best, best_key) if best_key else None

    def put(self, key: str, family: str, vec: list[float] | None, status: int, ctype: str, body: bytes):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?,?,0)",
                            (key, family, json.dumps(vec) if vec else None, body, status, ctype, time.time()))
            self.db.commit()
            if vec:
                self._vecs[key] = (family, vec)

    def purge(self) -> int:
        with self.lock:
            cur = self.db.execute("DELETE FROM entries WHERE created < ?", (time.time() - TTL,))
            self.db.commit()
            self._vecs = {k: v for k, v in self._vecs.items()
                          if self.db.execute("SELECT 1 FROM entries WHERE key=?", (k,)).fetchone()}
            return cur.rowcount

    def count(self) -> int:
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


# ----------------------------------------------------------------------------- policy
def cache_key(req: dict) -> str:
    """Exact key: model + role/content of every message, whitespace-normalized."""
    msgs = [(m.get("role", ""), " ".join(str(m.get("content", "")).split())) for m in req.get("messages", [])]
    raw = json.dumps([req.get("model", ""), msgs], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def model_family(model: str) -> str:
    """'opencode3/@cf/meta/llama-3.1-8b-instruct-fast' → 'llama-3.1'. Semantic hits never
    cross families; a llama answer must not be served for a gemini question."""
    m = model.lower().rsplit("/", 1)[-1]
    for sep in (":", "@"):
        m = m.split(sep)[0]
    parts = m.split("-")
    return "-".join(parts[:2]) if len(parts) > 1 else m


def cacheable(req: dict) -> tuple[bool, str]:
    if req.get("stream"):
        return False, "stream"
    if req.get("tools") or req.get("functions") or req.get("tool_choice"):
        return False, "tools"
    if float(req.get("temperature", 0) or 0) > MAX_TEMP:
        return False, "temperature"
    if not req.get("messages"):
        return False, "no-messages"
    if req.get("n", 1) != 1:
        return False, "n>1"
    return True, "ok"


def embed_text(req: dict) -> str:
    """What we embed: system prompt + the LAST user turn. Earlier turns change the
    answer less than the final question does, and this keeps vectors comparable
    across chats with different histories."""
    sys_ = " ".join(str(m.get("content", "")) for m in req["messages"] if m.get("role") == "system")
    user = next((str(m.get("content", "")) for m in reversed(req["messages"]) if m.get("role") == "user"), "")
    return (sys_ + "\n" + user).strip()[:8000]


# ----------------------------------------------------------------------------- embed client
class Embedder:
    def __init__(self, base: str, model: str):
        self.base, self.model = base, model
        self.available = True
        self.last_error = ""

    def __call__(self, text: str) -> list[float] | None:
        body = json.dumps({"model": self.model, "prompt": text}).encode()
        rq = urllib.request.Request(f"{self.base}/api/embeddings", body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(rq, timeout=10) as r:
                self.available = True
                return json.load(r).get("embedding")
        except (urllib.error.URLError, OSError, ValueError) as e:  # ollama down → exact-only mode
            self.available, self.last_error = False, str(e)
            return None


# ----------------------------------------------------------------------------- metrics
class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.c = {"exact_hit": 0, "semantic_hit": 0, "miss": 0, "bypass": 0, "upstream_error": 0}
        self.saved_ms = 0.0

    def inc(self, k: str, saved_ms: float = 0.0):
        with self.lock:
            self.c[k] += 1
            self.saved_ms += saved_ms

    def snapshot(self, store: Store, emb: Embedder) -> dict:
        with self.lock:
            hits = self.c["exact_hit"] + self.c["semantic_hit"]
            total = hits + self.c["miss"]
            return {**self.c, "hit_rate": round(hits / total, 4) if total else 0.0,
                    "entries": store.count(), "embedder_available": emb.available,
                    "embedder_error": emb.last_error, "threshold": THRESHOLD, "ttl_s": TTL,
                    "upstream_requests_avoided": hits}

    def prometheus(self, store: Store, emb: Embedder) -> str:
        s = self.snapshot(store, emb)
        lines = ["# TYPE semcache_requests_total counter"]
        for k in ("exact_hit", "semantic_hit", "miss", "bypass", "upstream_error"):
            lines.append(f'semcache_requests_total{{result="{k}"}} {s[k]}')
        lines += ["# TYPE semcache_entries gauge", f"semcache_entries {s['entries']}",
                  "# TYPE semcache_embedder_up gauge", f"semcache_embedder_up {int(s['embedder_available'])}"]
        return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- handler
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "semcache/0.1"
    store: Store
    embedder: Embedder
    stats: Stats
    upstream: str

    def log_message(self, *a):  # quiet; metrics are the log
        pass

    # ---- admin
    def do_GET(self):
        if self.path == "/semcache/stats":
            return self._json(200, self.stats.snapshot(self.store, self.embedder))
        if self.path == "/metrics":
            body = self.stats.prometheus(self.store, self.embedder).encode()
            return self._raw(200, "text/plain; version=0.0.4", body, {})
        if self.path == "/semcache/healthz":
            return self._json(200, {"ok": True})
        return self._relay()

    def do_DELETE(self):
        if self.path == "/semcache/purge":
            return self._json(200, {"purged": self.store.purge()})
        return self._relay()

    def do_POST(self):
        if self.path.split("?")[0] not in CACHEABLE_PATHS:
            return self._relay()
        body = self._body()
        try:
            req = json.loads(body or b"{}")
        except ValueError:
            return self._relay(body)
        ok, why = cacheable(req)
        if not ok:
            self.stats.inc("bypass")
            return self._relay(body, extra={"X-Semcache": f"bypass:{why}"})

        key = cache_key(req)
        hit = self.store.get_exact(key)
        if hit:
            self.stats.inc("exact_hit")
            return self._raw(hit[0], hit[1], hit[2], {"X-Semcache": "hit:exact"})

        fam = model_family(req.get("model", ""))
        vec = self.embedder(embed_text(req))
        if vec:
            near = self.store.nearest(fam, vec)
            if near and near[0] >= THRESHOLD:
                h = self.store.get_exact(near[1])
                if h:
                    self.stats.inc("semantic_hit")
                    return self._raw(h[0], h[1], h[2], {"X-Semcache": f"hit:semantic;score={near[0]:.4f}"})

        t0 = time.time()
        status, ctype, resp, hdrs = self._upstream(body)
        ms = (time.time() - t0) * 1000
        if status == 200 and ctype.startswith("application/json"):
            self.store.put(key, fam, vec, status, ctype, resp)
            self.stats.inc("miss")
            tag = "miss;stored" + ("" if vec else ";exact-only")
        else:
            self.stats.inc("upstream_error" if status >= 500 else "miss")
            tag = f"miss;not-stored;status={status}"
        hdrs["X-Semcache"] = tag
        return self._raw(status, ctype, resp, hdrs)

    # ---- plumbing
    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _fwd_headers(self) -> dict:
        return {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}

    def _upstream(self, body: bytes, method: str = "POST") -> tuple[int, str, bytes, dict]:
        rq = urllib.request.Request(self.upstream + self.path, body or None, self._fwd_headers(), method=method)
        try:
            with urllib.request.urlopen(rq, timeout=300) as r:
                h = {k: v for k, v in r.headers.items() if k.lower() not in HOP_HEADERS}
                return r.status, r.headers.get("Content-Type", "application/octet-stream"), r.read(), h
        except urllib.error.HTTPError as e:
            h = {k: v for k, v in e.headers.items() if k.lower() not in HOP_HEADERS}
            return e.code, e.headers.get("Content-Type", "application/json"), e.read(), h
        except (urllib.error.URLError, OSError) as e:
            return 502, "application/json", json.dumps({"error": {"message": f"semcache: upstream unreachable: {e}",
                                                                   "type": "upstream_error"}}).encode(), {}

    def _relay(self, body: bytes | None = None, extra: dict | None = None):
        if body is None:
            body = self._body()
        status, ctype, resp, hdrs = self._upstream(body, method=self.command)
        hdrs.update(extra or {})
        return self._raw(status, ctype, resp, hdrs)

    def _raw(self, status: int, ctype: str, body: bytes, hdrs: dict):
        self.send_response(status)
        hdrs = {k: v for k, v in hdrs.items() if k.lower() not in HOP_HEADERS and k.lower() != "content-type"}
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict):
        self._raw(status, "application/json", json.dumps(obj).encode(), {})


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(port: int, upstream: str, store: Store, embedder: Embedder, stats: Stats | None = None,
                host: str = "127.0.0.1") -> Server:
    h = type("H", (Handler,), {"store": store, "embedder": embedder, "stats": stats or Stats(), "upstream": upstream})
    return Server((host, port), h)


def main() -> int:
    store, emb = Store(DB_PATH), Embedder(OLLAMA, EMBED_MODEL)
    srv = make_server(PORT, UPSTREAM, store, emb, host=os.environ.get("SEMCACHE_BIND", "127.0.0.1"))
    print(f"semcache :{PORT} → {UPSTREAM}  embed={OLLAMA}/{EMBED_MODEL}  θ={THRESHOLD}  db={DB_PATH}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
