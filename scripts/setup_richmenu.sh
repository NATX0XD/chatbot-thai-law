#!/usr/bin/env bash
# Upload the rich menu and make it the default for every user of the channel.
#
#   scripts/setup_richmenu.sh            create and set as default
#   scripts/setup_richmenu.sh --prune    also delete the channel's other menus
#
# Three calls, in this order and no other: the definition has to exist before
# the image can be attached to it, and LINE refuses to make a menu the default
# until it has an image.
set -uo pipefail
cd "$(dirname "$0")/.."

IMAGE=assets/richmenu/richmenu-2500.png
DEF=assets/richmenu/richmenu.json
PRUNE=${1:-}

[ -f "$IMAGE" ] || { echo "ไม่พบ $IMAGE -- รัน python scripts/make_richmenu.py ก่อน"; exit 1; }

TOKEN=$(sed -n 's/^LINE_CHANNEL_ACCESS_TOKEN=//p' .env | tail -1)
[ -n "$TOKEN" ] || { echo "ไม่พบ LINE_CHANNEL_ACCESS_TOKEN ใน .env"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"

echo "==> สร้าง rich menu จาก $DEF"
created=$(curl -s -X POST https://api.line.me/v2/bot/richmenu \
  -H "$AUTH" -H "Content-Type: application/json" --data-binary @"$DEF")
ID=$(printf '%s' "$created" | sed -n 's/.*"richMenuId":"\([^"]*\)".*/\1/p')
[ -n "$ID" ] || { echo "    สร้างไม่สำเร็จ: $created"; exit 1; }
echo "    $ID"

echo "==> อัปโหลดรูป $IMAGE ($(wc -c <"$IMAGE" | tr -d ' ') bytes)"
code=$(curl -s -o /tmp/richmenu-upload.txt -w '%{http_code}' -X POST \
  "https://api-data.line.me/v2/bot/richmenu/$ID/content" \
  -H "$AUTH" -H "Content-Type: image/png" --data-binary @"$IMAGE")
if [ "$code" != "200" ]; then
  echo "    HTTP $code: $(cat /tmp/richmenu-upload.txt)"
  # a menu with no image can never be shown, so do not leave it behind
  curl -s -X DELETE "https://api.line.me/v2/bot/richmenu/$ID" -H "$AUTH" >/dev/null
  exit 1
fi
echo "    HTTP 200"

echo "==> ตั้งเป็นเมนูเริ่มต้นของทุกคน"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  "https://api.line.me/v2/bot/user/all/richmenu/$ID" -H "$AUTH")
echo "    HTTP $code"
[ "$code" = "200" ] || exit 1

others=$(curl -s https://api.line.me/v2/bot/richmenu/list -H "$AUTH" \
  | tr ',' '\n' | sed -n 's/.*"richMenuId":"\([^"]*\)".*/\1/p' | grep -v "^$ID$")

if [ -n "$others" ]; then
  if [ "$PRUNE" = "--prune" ]; then
    echo "==> ลบเมนูเก่า"
    for old in $others; do
      curl -s -X DELETE "https://api.line.me/v2/bot/richmenu/$old" -H "$AUTH" >/dev/null
      echo "    ลบ $old"
    done
  else
    echo "==> ยังมีเมนูเก่าค้างอยู่ (ไม่ได้ถูกใช้) สั่ง --prune เพื่อลบ"
    printf '    %s\n' $others
  fi
fi

echo "เรียบร้อย เปิดแชทกับบอทใหม่อีกครั้งจะเห็นเมนู"
