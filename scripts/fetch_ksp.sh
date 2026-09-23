#!/usr/bin/env bash
# Download the ten Teachers Council documents that define professional ethics.
#
#   scripts/fetch_ksp.sh
#
# These are the nine documents listed under "จรรยาบรรณวิชาชีพ" on
# https://www.ksp.or.th/laws/ plus the Act they are issued under. Seven come
# from the Royal Gazette directly; three are only published on the Council's
# own site. data/raw/ is gitignored, so this is how a fresh clone gets them.
#
# Checked on 23 September 2026: none of these appear in iapp/rag_thai_laws or
# pythainlp/thailaw, the sources the general-law corpus was built from, which
# is why they have to be fetched as PDFs and parsed here.
#
# The checksums pin the exact file each URL served on that date. A mismatch
# means the publisher replaced the document -- look at what changed before
# updating the hash, because the section numbering may have moved with it.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw/ksp

fail=0

# key|sha256|url|label
DOCS=(
"ksp-2556|2c3fa473a259ddbd925d9697b7fa114190773447d31ee7e504ce9b570e776f7e|https://ratchakitcha.soc.go.th/documents/1986083.pdf|ข้อบังคับคุรุสภา ว่าด้วยจรรยาบรรณของวิชาชีพ พ.ศ. 2556"
"ksp-2550|407f62549262423ab09301a329e5dba194099428b155fb8656058ac06a18057c|https://ratchakitcha.soc.go.th/documents/214339.pdf|ข้อบังคับคุรุสภา ว่าด้วยแบบแผนพฤติกรรมตามจรรยาบรรณของวิชาชีพ พ.ศ. 2550"
"act-2546|f07488b7f91ee88278c6f35cfac5fca6ca6be069ef3385626fb11cec960af533|https://www.ksp.or.th/wp-content/uploads/2023/05/1-พระราชบัญญัติสภาครูและบุคลากรทางการศึกษา-พ.ศ.-2546.pdf|พระราชบัญญัติสภาครูและบุคลากรทางการศึกษา พ.ศ. 2546"
"ksp-2553|0c6385a09c5e99fdc417422603bbfac756d1ab6d7756ed94aad70825330ce7f2|https://ratchakitcha.soc.go.th/documents/1863175.pdf|ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณของวิชาชีพ พ.ศ. 2553"
"ksp-2559|79a2d1c8b64ba2771ef8f11d7521f76443655f930c406d37069f5973df487a3f|https://ratchakitcha.soc.go.th/documents/2080413.pdf|ข้อบังคับฯ การพิจารณาการประพฤติผิดจรรยาบรรณ (ฉบับที่ 2) พ.ศ. 2559"
"ksp-2563|c0f3692f1690547690f03761211a7c3344bbe45eb641ee5da3c7e0cbc209db41|https://ratchakitcha.soc.go.th/documents/17142857.pdf|ข้อบังคับฯ การพิจารณาการประพฤติผิดจรรยาบรรณ (ฉบับที่ 3) พ.ศ. 2563"
"ksp-2568|f175ee96e6063c68d1b39e3fa185d4b8c8eb94c3404eade4f1c881b20ba19f27|https://www.ksp.or.th/wp-content/uploads/2025/07/ข้อบังคับ​คุรุสภา​ฯการพิจารณา​การประพฤต.pdf|ข้อบังคับคุรุสภา ว่าด้วยการพิจารณาการประพฤติผิดจรรยาบรรณของวิชาชีพ พ.ศ. 2568"
"ksp-2549|6782e372de0a1a118a446b8a3a976a6952a9139b4980f21511b7b0b364f6cfc5|https://ratchakitcha.soc.go.th/documents/204062.pdf|ข้อบังคับคุรุสภา ว่าด้วยการอุทธรณ์คำวินิจฉัยการประพฤติผิดจรรยาบรรณของวิชาชีพ พ.ศ. 2549"
"ksp-2569|fd3c9061cf046593fc46f88aa6cdc6155f6b9f896286303063a6d82cca4b07ac|https://www.ksp.or.th/wp-content/uploads/2026/04/ข้อบังคับ-อุทธรณ์จรรยบรรณฯ-ฉ.2-พ.ศ.2569-8เม.ย.69.pdf|ข้อบังคับฯ การอุทธรณ์คำวินิจฉัย (ฉบับที่ 2) พ.ศ. 2569"
"ksp-ann-appeal|6eb15c8acb123cd4a59146bf348d9d8a3fc318d9c8f3634908e3d20dc668152a|https://ratchakitcha.soc.go.th/documents/1826563.pdf|ประกาศคณะกรรมการคุรุสภา เรื่อง หลักเกณฑ์และวิธีการได้มาซึ่งคณะอนุกรรมการอุทธรณ์ฯ"
)

check() {
  local want=$1 path=$2
  [ "$(shasum -a 256 <"$path" | cut -d' ' -f1)" = "$want" ]
}

for row in "${DOCS[@]}"; do
  IFS='|' read -r key want url label <<<"$row"
  out="data/raw/ksp/$key.pdf"

  if [ -s "$out" ] && check "$want" "$out"; then
    echo "มีอยู่แล้ว: $out"
    continue
  fi

  echo "==> ดาวน์โหลด $key — $label"
  if ! curl -fsSL --max-time 120 -o "$out" "$url"; then
    echo "    ล้มเหลว: $url"
    rm -f "$out"
    fail=1
    continue
  fi

  if check "$want" "$out"; then
    echo "    $(wc -c <"$out" | tr -d ' ') bytes"
  else
    echo "    checksum ไม่ตรง — ต้นทางเปลี่ยนไฟล์แล้ว ตรวจก่อนแก้ค่าในสคริปต์นี้"
    echo "    ที่ได้: $(shasum -a 256 <"$out" | cut -d' ' -f1)"
    echo "    ที่คาด: $want"
    fail=1
  fi
done

echo
if [ "$fail" -ne 0 ]; then
  echo "มีเอกสารที่ดึงไม่สำเร็จหรือ checksum ไม่ตรง — อย่าเพิ่งสร้าง corpus"
  exit 1
fi

echo "ครบทั้ง ${#DOCS[@]} ฉบับใน data/raw/ksp/"
echo "ต่อไป: python -m ingest.extract_ksp"
