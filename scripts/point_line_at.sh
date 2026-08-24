#!/usr/bin/env bash
# Point the LINE webhook at a given base URL, then make LINE prove it can reach it.
#
#   scripts/point_line_at.sh https://thai-law-bot.onrender.com
#
# scripts/serve_tunnel.sh does this for a throwaway cloudflared hostname on every
# start. This is the same two calls for a permanent host, so switching from the
# local tunnel to the deployed service is one command instead of a console visit.
#
# LINE's verify call is the part that matters: registering an endpoint always
# returns 200, even for a hostname that resolves to nothing, so a registration
# alone tells you nothing about whether the bot will actually receive anything.
set -uo pipefail
cd "$(dirname "$0")/.."

URL="${1:-}"
[ -n "$URL" ] || { echo "usage: $0 https://<host>   (ไม่ต้องใส่ /webhook)"; exit 1; }
URL="${URL%/}"
URL="${URL%/webhook}"

TOKEN=$(sed -n 's/^LINE_CHANNEL_ACCESS_TOKEN=//p' .env | tail -1)
[ -n "$TOKEN" ] || { echo "ไม่พบ LINE_CHANNEL_ACCESS_TOKEN ใน .env"; exit 1; }

# refuse to point LINE at something that is not serving this bot: a typo here
# goes silent, and the only symptom is a bot that stops answering
echo "==> ตรวจ $URL/health"
health=$(curl -s --max-time 15 "$URL/health")
case "$health" in
  *'"status":"ok"'*) echo "    $health" ;;
  *) echo "    ไม่ใช่บอทตัวนี้หรือยังไม่ขึ้น: ${health:-<ว่าง>}"; exit 1 ;;
esac

echo "==> ตั้ง webhook เป็น $URL/webhook"
code=$(curl -s -o /dev/null -w '%{http_code}' -X PUT \
  https://api.line.me/v2/bot/channel/webhook/endpoint \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"endpoint\":\"$URL/webhook\"}")
echo "    HTTP $code"

echo "==> ให้ LINE ยิงทดสอบ"
verdict=$(curl -s -X POST https://api.line.me/v2/bot/channel/webhook/test \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}')
echo "    $verdict"

case "$verdict" in
  *'"success":true'*) echo "เรียบร้อย ปิด tunnel ในเครื่องได้แล้ว" ;;
  *) echo "verify ไม่ผ่าน webhook ยังชี้ที่เดิมในทางปฏิบัติ"; exit 1 ;;
esac
