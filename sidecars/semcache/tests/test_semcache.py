"""End-to-end tests for semcache with a fake gateway and a fake Ollama.

Run: python3 -m unittest discover -s sidecars/semcache/tests
"""
import http.server
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import semcache  # noqa: E402

# Deterministic fake embeddings: similar sentences → near-identical vectors.
VECS = {
    "capital of france": [1.0, 0.0, 0.0],
    "france capital":    [0.99, 0.14, 0.0],   # cosine ≈ 0.99 with the above
    "capital of peru":   [0.0, 1.0, 0.0],     # orthogonal
}


def fake_embed(text: str):
    t = text.lower()
    for k, v in VECS.items():
        if k in t:
            return v
    return [0.0, 0.0, 1.0]


class FakeGateway(http.server.BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        FakeGateway.calls.append((self.path, body, self.headers.get("Authorization")))
        if self.headers.get("Authorization") != "Bearer fbu_test":
            return self._j(401, {"error": "unauthorized"})
        if body.get("model") == "boom":
            return self._j(503, {"error": "provider down"})
        return self._j(200, {"id": f"r{len(FakeGateway.calls)}", "model": body.get("model"),
                             "choices": [{"message": {"role": "assistant",
                                                      "content": f"answer #{len(FakeGateway.calls)}"}}]})

    def do_GET(self):
        FakeGateway.calls.append((self.path, None, None))
        self._j(200, {"object": "list", "data": [{"id": "m"}]})

    def _j(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Upstream", "fake")
        self.end_headers()
        self.wfile.write(b)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gw = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeGateway)
        threading.Thread(target=cls.gw.serve_forever, daemon=True).start()
        cls.store = semcache.Store(":memory:")
        cls.emb = semcache.Embedder("http://127.0.0.1:1", "fake")
        cls.emb.__class__ = type("E", (semcache.Embedder,), {"__call__": lambda s, t: fake_embed(t)})
        cls.stats = semcache.Stats()
        cls.srv = semcache.make_server(0, f"http://127.0.0.1:{cls.gw.server_port}", cls.store, cls.emb, cls.stats)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.gw.shutdown()

    def setUp(self):
        FakeGateway.calls.clear()
        # fresh store per test — the handler class holds a reference, so swap in place
        fresh = semcache.Store(":memory:")
        self.srv.RequestHandlerClass.store = fresh
        self.__class__.store = fresh

    def chat(self, content, model="cf/llama-3.1-8b-instruct-fast", key="fbu_test", **extra):
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": content}], **extra}).encode()
        rq = urllib.request.Request(self.base + "/v1/chat/completions", body,
                                    {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(rq) as r:
                return r.status, json.load(r), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.load(e), e.headers

    # ---- core policy
    def test_miss_then_exact_hit(self):
        s, b1, h1 = self.chat("What is the capital of France?")
        self.assertEqual(s, 200); self.assertTrue(h1["X-Semcache"].startswith("miss;stored"))
        s, b2, h2 = self.chat("What is the capital of France?")
        self.assertEqual(h2["X-Semcache"], "hit:exact")
        self.assertEqual(b1, b2)
        self.assertEqual(len(FakeGateway.calls), 1, "second call must not reach the gateway")

    def test_semantic_hit_same_family(self):
        self.chat("Tell me the capital of France please")
        s, b, h = self.chat("France capital?")
        self.assertTrue(h["X-Semcache"].startswith("hit:semantic"), h["X-Semcache"])
        self.assertEqual(len(FakeGateway.calls), 1)

    def test_no_cross_family_semantic_hit(self):
        self.chat("capital of France", model="cf/llama-3.1-8b")
        s, b, h = self.chat("France capital", model="google/gemini-2.5-flash")
        self.assertTrue(h["X-Semcache"].startswith("miss"), "gemini must not get a llama answer")
        self.assertEqual(len(FakeGateway.calls), 2)

    def test_dissimilar_is_miss(self):
        self.chat("capital of France")
        s, b, h = self.chat("capital of Peru")
        self.assertTrue(h["X-Semcache"].startswith("miss"))

    # ---- bypass rules
    def test_stream_tools_temperature_bypass(self):
        for kw, why in (({"stream": True}, "stream"), ({"tools": [{"type": "function"}]}, "tools"),
                        ({"temperature": 0.9}, "temperature")):
            s, b, h = self.chat("anything unique " + why, **kw)
            self.assertEqual(h["X-Semcache"], f"bypass:{why}")
        self.assertEqual(len(FakeGateway.calls), 3)

    # ---- passthrough contract
    def test_non_cacheable_path_relayed_verbatim(self):
        with urllib.request.urlopen(self.base + "/v1/models") as r:
            self.assertEqual(r.headers["X-Upstream"], "fake")
            self.assertEqual(json.load(r)["object"], "list")

    def test_auth_header_forwarded_and_401_not_cached(self):
        s, b, h = self.chat("secret question", key="wrong")
        self.assertEqual(s, 401); self.assertIn("not-stored", h["X-Semcache"])
        s, b, h = self.chat("secret question", key="fbu_test")
        self.assertEqual(s, 200); self.assertIn("miss", h["X-Semcache"])

    def test_upstream_5xx_not_cached(self):
        s, b, h = self.chat("x", model="boom")
        self.assertEqual(s, 503)
        s, b, h = self.chat("x", model="boom")
        self.assertEqual(len(FakeGateway.calls), 2, "errors must never be served from cache")

    def test_upstream_down_is_502(self):
        srv = semcache.make_server(0, "http://127.0.0.1:1", semcache.Store(":memory:"), self.emb)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        rq = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/v1/chat/completions",
                                    json.dumps({"model": "m", "messages": [{"role": "user", "content": "q"}]}).encode(),
                                    {"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(rq)
        self.assertEqual(cm.exception.code, 502)
        srv.shutdown()

    # ---- degraded mode + observability
    def test_embedder_down_falls_back_to_exact_only(self):
        emb = semcache.Embedder("http://127.0.0.1:1", "none")  # nothing listening
        store = semcache.Store(":memory:")
        srv = semcache.make_server(0, f"http://127.0.0.1:{self.gw.server_port}", store, emb)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"
        for _ in range(2):
            rq = urllib.request.Request(base + "/v1/chat/completions",
                                        json.dumps({"model": "m", "messages": [{"role": "user", "content": "q"}]}).encode(),
                                        {"Content-Type": "application/json", "Authorization": "Bearer fbu_test"})
            with urllib.request.urlopen(rq) as r:
                tag = r.headers["X-Semcache"]
        self.assertEqual(tag, "hit:exact")
        self.assertFalse(emb.available)
        srv.shutdown()

    def test_stats_and_metrics(self):
        with urllib.request.urlopen(self.base + "/semcache/stats") as r:
            s = json.load(r)
        self.assertIn("hit_rate", s); self.assertIn("upstream_requests_avoided", s)
        with urllib.request.urlopen(self.base + "/metrics") as r:
            self.assertIn('semcache_requests_total{result="exact_hit"}', r.read().decode())

    # ---- unit
    def test_model_family(self):
        f = semcache.model_family
        self.assertEqual(f("opencode3/@cf/meta/llama-3.1-8b-instruct-fast"), "llama-3.1")
        self.assertEqual(f("qwen2.5:3b"), "qwen2.5")
        self.assertEqual(f("gemini-2.5-flash"), "gemini-2.5")
        self.assertNotEqual(f("llama-3.1-8b"), f("llama-3.3-70b"))

    def test_cache_key_whitespace_insensitive(self):
        a = semcache.cache_key({"model": "m", "messages": [{"role": "user", "content": "hi   there"}]})
        b = semcache.cache_key({"model": "m", "messages": [{"role": "user", "content": "hi there"}]})
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
