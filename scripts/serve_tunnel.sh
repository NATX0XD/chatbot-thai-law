#!/usr/bin/env bash
# Open a Cloudflare quick tunnel and point the LINE webhook at it.
#
# Quick tunnels get a throwaway hostname that dies whenever cloudflared restarts,
# and the LINE webhook keeps pointing at the dead one -- which is exactly how this
# bot went silent. So the URL is re-registered with LINE on every start, and the
# script stays in the foreground so launchd can restart the pair together.
#
# A named tunnel would give a stable hostname, but it needs a Cloudflare account
# and a domain. This keeps the zero-setup path working.
set -uo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
LOG_DIR="${LOG_DIR:-$HOME/Library/Logs/thai-law-bot}"
mkdir -p "$LOG_DIR"
TUNNEL_LOG="$LOG_DIR/tunnel.log"

say() { echo "$(date '+%Y-%m-%d %H:%M:%S') [tunnel] $*"; }

# --- wait for the app to answer before exposing it ---------------------------
for _ in $(seq 1 60); do
  curl -sf --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null && break
  sleep 2
done
if ! curl -sf --max-time 3 "http://127.0.0.1:$PORT/health" >/dev/null; then
  say "app on port $PORT never became healthy; giving up so launchd retries"
  exit 1
fi

# --- start the tunnel --------------------------------------------------------
: > "$TUNNEL_LOG"
cloudflared tunnel --url "http://127.0.0.1:$PORT" >>"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill "$TUNNEL_PID" 2>/dev/null' EXIT INT TERM

URL=""
for _ in $(seq 1 45); do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$TUNNEL_LOG" | head -1)
  [ -n "$URL" ] && break
  kill -0 "$TUNNEL_PID" 2>/dev/null || { say "cloudflared exited early"; exit 1; }
  sleep 2
done
[ -n "$URL" ] || { say "no tunnel hostname appeared"; exit 1; }
say "tunnel up at $URL"

# --- tell LINE where to find us ---------------------------------------------
TOKEN=$(sed -n 's/^LINE_CHANNEL_ACCESS_TOKEN=//p' .env | tail -1)
if [ -n "$TOKEN" ]; then
  # the hostname needs a moment to propagate before LINE's verifier can resolve it
  sleep 5
  code=$(curl -s -o /dev/null -w '%{http_code}' -X PUT \
    https://api.line.me/v2/bot/channel/webhook/endpoint \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"endpoint\":\"$URL/webhook\"}")
  say "registered webhook with LINE (HTTP $code)"
  verdict=$(curl -s -X POST https://api.line.me/v2/bot/channel/webhook/test \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}')
  say "LINE verify: $verdict"
else
  say "no LINE token in .env; skipping webhook registration"
fi

echo "$URL" > "$LOG_DIR/current-url.txt"

# Hold the foreground. If cloudflared dies, this exits and launchd starts the
# whole thing again -- including re-registering the new hostname.
wait "$TUNNEL_PID"
say "cloudflared exited with status $?"
