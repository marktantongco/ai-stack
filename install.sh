#!/usr/bin/env bash
# ai-stack installer — full local AI agent stack in one command.
#
# Installs, in order:
#   1. freebuff-unified gateway + sidecars (via unified-freebuff-proxy
#      scripts/install-omarchy.sh — the canonical gateway installer)
#   2. owl-agent stack (:60000 proxy defense + chameleon fingerprints)
#   3. Verifies every door, prints the opencode provider block to paste
#
# Usage:
#   ./install.sh [--yes] [--skip-owl] [--verify-only]
#
# Flags:
#   --yes         assume yes to prompts
#   --skip-owl    gateway only (skip owl-agent install/verify)
#   --verify-only probe live endpoints, change nothing
#
# Env:
#   AI_STACK_GATEWAY_DIR  gateway checkout dir (default ~/workspace/freebuff-unified)
#   AI_STACK_GATEWAY_REF  gateway git ref to install (default: pinned commit below)
#
# Secrets: never written. Gateway config.yaml keeps CHANGE_ME placeholders
# until you fill keys, then `sudo systemctl restart freebuff-unified`.
# Exit codes: 0 ok, 1 usage/error, 2 verify failed.

set -euo pipefail

if [ -t 1 ]; then
  B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; X=$'\033[0m'
else
  B=""; G=""; Y=""; R=""; X=""
fi
step() { printf '%s\n' "${B}==>${X} $*"; }
info() { printf '%s\n' "    $*"; }
ok()   { printf '%s\n' "    ${G}OK${X}  $*"; }
warn() { printf '%s\n' "    ${Y}!!${X}  $*"; }
die()  { printf '%s\n' "${R}error:${X} $*" >&2; exit 1; }
fail() { printf '%s\n' "${R}error:${X} $*" >&2; exit 2; }   # verify failed

YES=0 SKIP_OWL=0 VERIFY_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1; shift ;;
    --skip-owl) SKIP_OWL=1; shift ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) die "unknown flag: $1 (see --help)" ;;
  esac
done
YESFLAG=""; [ "$YES" -eq 1 ] && YESFLAG="--yes"

for dep in curl git; do command -v "$dep" >/dev/null 2>&1 || die "missing dependency: $dep"; done

GATEWAY_REPO="https://github.com/marktantongco/unified-freebuff-proxy.git"
# Pinned upstream commit: a push to unified-freebuff-proxy/main can no longer break this
# installer silently. Bump deliberately: AI_STACK_GATEWAY_REF=main ./install.sh  (or edit here).
GATEWAY_REF="${AI_STACK_GATEWAY_REF:-9618530081c4342593b1e7113633b6bf180e4a60}"   # 2026-09-14
# Gateway checkout dir: override with AI_STACK_GATEWAY_DIR (no machine-specific paths here).
GATEWAY_DIR="${AI_STACK_GATEWAY_DIR:-$HOME/workspace/freebuff-unified}"

probe() { # path expect [bearer]
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 10 ${3:+-H "Authorization: Bearer $3"} "http://127.0.0.1:18080$1" 2>/dev/null) || code=000
  [ "$code" = "$2" ] && ok "$1 -> $code" || { warn "$1 -> $code (want $2)"; return 1; }
}

# ---------------------------------------------------------------- 1. gateway
step "1/3 gateway (delegates to canonical installer)"
if [ "$VERIFY_ONLY" -eq 0 ]; then
  if [ ! -d "$GATEWAY_DIR/.git" ]; then
    git clone "$GATEWAY_REPO" "$GATEWAY_DIR" || die "clone failed (offline?)"
  fi
  if [ "$GATEWAY_REF" != "main" ]; then
    git -C "$GATEWAY_DIR" fetch -q origin "$GATEWAY_REF" 2>/dev/null || git -C "$GATEWAY_DIR" fetch -q origin
    git -C "$GATEWAY_DIR" checkout -q --detach "$GATEWAY_REF" || die "cannot check out pinned gateway ref $GATEWAY_REF"
    info "gateway pinned at ${GATEWAY_REF:0:12}"
  fi
  if [ -x "$GATEWAY_DIR/scripts/install-omarchy.sh" ]; then
    "$GATEWAY_DIR/scripts/install-omarchy.sh" $YESFLAG --repo-dir "$GATEWAY_DIR" \
      || die "gateway installer failed"
  else
    die "gateway installer missing: $GATEWAY_DIR/scripts/install-omarchy.sh"
  fi
else
  info "verify-only: skipping gateway install"
fi

# ------------------------------------------------------------------- 2. owl
step "2/3 owl-agent stack"
if [ "$SKIP_OWL" -eq 1 ]; then
  info "skipped (--skip-owl)"
elif [ "$VERIFY_ONLY" -eq 1 ]; then
  info "verify-only: skipping owl-agent install"
else
  if systemctl is-active --quiet owl-agent.service 2>/dev/null \
      || sudo systemctl is-active --quiet owl-agent.service 2>/dev/null; then
    ok "owl-agent.service active"
  else
    warn "owl-agent.service not active — install unified-owl stack first:"
    warn "  git clone https://github.com/marktantongco/unified-owl.git ~/workspace/unified-owl"
    warn "  see unified-owl README + owl-sync for x1/root sync"
  fi
fi

# ----------------------------------------------------------------- 3. verify
step "3/3 verify all doors"
fails=0
KEY="$(grep -oE 'fbu_[A-Za-z0-9_]+' "$GATEWAY_DIR/config.yaml" 2>/dev/null | head -n 1 || true)"
[ -n "$KEY" ] || warn "no fbu_ key found in $GATEWAY_DIR/config.yaml — authed probes will 401"
case "$KEY" in fbu_CHANGE_ME*|fbu_change_me*) warn "config.yaml still has CHANGE_ME placeholder key";; esac
probe /healthz 200 || fails=$((fails+1))
probe /readyz 200 || fails=$((fails+1))
probe /health/all 200 || fails=$((fails+1))
probe /v1/models 200 "${KEY:-}" || fails=$((fails+1))
probe /v1/lmarena/evals 200 "${KEY:-}" || fails=$((fails+1))
probe /v1/lmarena/leaderboard 200 "${KEY:-}" || fails=$((fails+1))
if [ "$SKIP_OWL" -eq 0 ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 8 http://127.0.0.1:60000/health 2>/dev/null) || code=000
  [ "$code" = "200" ] && ok "/owl :60000/health -> $code" || { warn "owl :60000 -> $code"; fails=$((fails+1)); }
fi
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 http://127.0.0.1:18090/semcache/healthz 2>/dev/null) || code=000
[ "$code" = "200" ] && ok "semcache :18090 -> 200" || info "semcache :18090 not running (optional: sidecars/semcache/README.md)"
if [ "$fails" -eq 0 ]; then ok "stack verified"; else fail "stack verify: $fails failed"; fi

step "opencode provider block (paste into ~/.config/opencode/opencode.json)"
cat <<EOF
    "x3": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "X3 freebuff-unified (free, prod)",
      "options": {
        "baseURL": "http://127.0.0.1:18080/v1",
        "apiKey": "{env:FREEBUFF_API_KEY}"
      }
    }
EOF
step "done. fill keys in $GATEWAY_DIR/config.yaml, then: sudo systemctl restart freebuff-unified"
