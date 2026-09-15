#!/usr/bin/env python3
"""Generate provider-status.md and index.html from one source of truth.

Sources (merged, in priority order):
  1. Live gateway  GET :18080/health/all   -> infrastructure rows, last_verified = checked_at
  2. status/providers.yaml (hand-curated)  -> provider rows that the gateway cannot probe
                                              (wallet state, blocked reasons)
Output:
  provider-status.md   single truth table, one row per provider/component
  index.html           rendered from the same rows (never edit by hand)

Usage:
  scripts/gen-status.py [--gateway http://127.0.0.1:18080] [--offline] [--check]

  --offline  skip the gateway probe; reuse last_verified values already in the yaml
  --check    exit 1 if the generated files differ from what is on disk (CI drift gate)
"""
import argparse
import datetime as dt
import html
import json
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "status" / "providers.yaml"
MD = ROOT / "provider-status.md"
HTML = ROOT / "index.html"

STATE_ICON = {"live": "✅", "wallet": "⚠️", "blocked": "❌", "down": "❌", "unknown": "❔"}
STATE_LABEL = {"live": "LIVE", "wallet": "WALLET-GATED", "blocked": "BLOCKED",
               "down": "DOWN", "unknown": "UNKNOWN"}
STATE_CLASS = {"live": "ok", "wallet": "warn", "blocked": "err", "down": "err", "unknown": "warn"}


# --------------------------------------------------------------------------- yaml (tiny subset)
def load_yaml(path: pathlib.Path) -> list[dict]:
    """Parse the very small YAML subset used by status/providers.yaml.

    Format: a list of flat mappings ("- key: value" blocks). No nesting, no anchors.
    Kept dependency-free so the script runs on a bare python3.
    """
    rows, cur = [], None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        if line.startswith("- "):
            cur = {}
            rows.append(cur)
            line = "  " + line[2:]
        if cur is None or ":" not in line:
            raise SystemExit(f"{path}: cannot parse line: {raw!r}")
        k, v = line.strip().split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        cur[k.strip()] = v
    return rows


# --------------------------------------------------------------------------- gateway
def probe_gateway(base: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base}/health/all", timeout=8) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def merge(rows: list[dict], health: dict | None) -> list[dict]:
    """Overlay live gateway results (keyed by `probe`) onto curated rows."""
    if not health:
        return rows
    results = health.get("results", {})
    checked = health.get("checked_at", "")
    for row in rows:
        key = row.get("probe")
        if key and key in results:
            r = results[key]
            row["state"] = "live" if r.get("ok") else "down"
            row["detail"] = f"HTTP {r.get('code', 0)}, {r.get('ms', 0)} ms" + (
                f" — {r['error']}" if r.get("error") else "")
            row["last_verified"] = checked
            row["source"] = "gateway /health/all"
    return rows


# --------------------------------------------------------------------------- render
def render_md(rows: list[dict], generated: str, live: bool) -> str:
    out = [
        "# AI Stack — Provider & Infrastructure Status",
        "",
        f"**Generated:** {generated}  ",
        f"**Source:** `scripts/gen-status.py` ({'live gateway + ' if live else ''}`status/providers.yaml`)  ",
        "**Do not edit by hand** — edit `status/providers.yaml` and re-run the generator.",
        "",
        "## Truth table",
        "",
        "| Kind | Name | State | Detail | Last verified | Source |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        st = r.get("state", "unknown")
        out.append(
            f"| {r.get('kind','')} | **{r.get('name','')}** | {STATE_ICON[st]} {STATE_LABEL[st]} | "
            f"{r.get('detail','')} | `{r.get('last_verified','never')}` | {r.get('source','manual')} |"
        )
    counts = {s: sum(1 for r in rows if r.get("state") == s) for s in STATE_LABEL}
    out += [
        "",
        "## Summary",
        "",
        "| State | Count |",
        "|---|---|",
    ] + [f"| {STATE_ICON[s]} {STATE_LABEL[s]} | {n} |" for s, n in counts.items() if n] + [
        "",
        "Rows whose **Source** is `gateway /health/all` are refreshed on every run; "
        "the rest are curated facts (wallet balances, account blocks) that no probe can see.",
        "",
    ]
    return "\n".join(out)


def render_html(rows: list[dict], generated: str) -> str:
    def tr(r: dict) -> str:
        st = r.get("state", "unknown")
        e = html.escape
        return (f"<tr><td>{e(r.get('kind',''))}</td><td>{e(r.get('name',''))}</td>"
                f"<td class=\"{STATE_CLASS[st]}\">{STATE_LABEL[st]}</td>"
                f"<td>{e(r.get('detail',''))}</td><td><code>{e(r.get('last_verified','never'))}</code></td></tr>")

    live = sum(1 for r in rows if r.get("state") == "live" and r.get("kind") == "provider")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Stack — Live Provider Status</title>
<meta name="description" content="Freebuff AI agent stack: live provider inference status and infrastructure health.">
<meta name="generator" content="scripts/gen-status.py">
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:3rem auto;padding:0 1rem;line-height:1.6}}code{{background:#f1f1f1;padding:.1rem .3rem;border-radius:4px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}}th{{background:#333;color:#fff}}.ok{{color:#2ea043;font-weight:bold}}.warn{{color:#d29922;font-weight:bold}}.err{{color:#da3633;font-weight:bold}}small{{color:#666}}</style>
</head>
<body>
<h1>AI Stack — Live Provider Status</h1>
<p>Self-hosted, privacy-first <strong>local AI agent infrastructure</strong> with multi-provider inference. <span class="ok">● {live} providers live</span></p>
<p><small>Generated {html.escape(generated)} by <code>scripts/gen-status.py</code> — do not edit by hand.</small></p>
<table>
<tr><th>Kind</th><th>Name</th><th>State</th><th>Detail</th><th>Last verified</th></tr>
{chr(10).join(tr(r) for r in rows)}
</table>
<h2>Quickstart</h2>
<pre><code># Login to unlock GLM in opencode
opencode run --model autoclaw/glm-5-turbo "hello"</code></pre>
<p>Full docs: <a href="https://github.com/marktantongco/ai-stack">README.md</a> | <a href="provider-status.md">Provider Status</a></p>
</body>
</html>
"""


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gateway", default="http://127.0.0.1:18080")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    rows = load_yaml(SRC)
    health = None if a.offline else probe_gateway(a.gateway)
    rows = merge(rows, health)
    if health:
        generated = health.get("checked_at", "")
    else:
        # deterministic in --check/--offline mode so CI diffs are stable
        generated = max((r.get("last_verified", "") for r in rows), default="") or \
            dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    md, page = render_md(rows, generated, bool(health)), render_html(rows, generated)
    if a.check:
        drift = [p.name for p, new in ((MD, md), (HTML, page)) if not p.exists() or p.read_text() != new]
        if drift:
            print(f"drift: {', '.join(drift)} are stale — run scripts/gen-status.py --offline", file=sys.stderr)
            return 1
        print("status files in sync")
        return 0
    MD.write_text(md, encoding="utf-8")
    HTML.write_text(page, encoding="utf-8")
    print(f"wrote {MD.name} and {HTML.name} ({len(rows)} rows, gateway={'live' if health else 'offline'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
