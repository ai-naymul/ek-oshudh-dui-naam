#!/usr/bin/env bash
# Demo networking: start the backend (which also serves the built web app) and a Cloudflare quick tunnel.
# No account or domain needed. Prints the public URL; open it on the laptop and press "ফোনে খুলুন" for the QR.
# If the tunnel drops, run this again: a new URL and QR in under a minute.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=$(mktemp -t ek_tunnel)
if ! curl -sf localhost:8000/health >/dev/null; then
  (cd web && npm run build >/dev/null)
  (cd backend && nohup uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/ek_api.log 2>&1 < /dev/null &)
  for _ in $(seq 30); do curl -sf localhost:8000/health >/dev/null && break; sleep 1; done
fi
nohup cloudflared tunnel --no-autoupdate --url http://localhost:8000 > "$LOG" 2>&1 < /dev/null & disown
for _ in $(seq 40); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)
  [ -n "${URL:-}" ] && break; sleep 1
done
[ -z "${URL:-}" ] && { echo "tunnel failed, see $LOG"; exit 1; }
for _ in $(seq 30); do curl -sf "$URL/health" >/dev/null && break; sleep 2; done
echo "$URL" > /tmp/ek_tunnel_url
echo "App + API:   $URL"
echo "Pages link:  https://ek-oshudh-dui-naam.pages.dev/?api=$URL"
echo "WhatsApp webhook (Meta dashboard): $URL/whatsapp/webhook"
