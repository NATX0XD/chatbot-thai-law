#!/usr/bin/env bash
# Download the two codes that the Act corpus does not contain.
#
#   scripts/fetch_codes.sh
#
# data/raw/ is gitignored, so a fresh clone has the Act parquet files missing too
# -- this fetches only the part that ingest/extract_codes.py needs, which is small
# enough to pull on demand (2.1 MB against the 383 MB of Act sources).
#
# Source: the PyThaiNLP thai-law project, which publishes ประมวลกฎหมายอาญา and
# ประมวลกฎหมายแพ่งและพาณิชย์ hand-checked and split one row per section. Public
# domain under the Copyright Act B.E. 2537 s.7, same terms as the Act corpus.
#
# Checked on 31 August 2026: neither code appears anywhere in iapp/rag_thai_laws
# or pythainlp/thailaw (42,755 documents, not one of them a code), which is why
# they have to come from here.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw

BASE=https://github.com/PyThaiNLP/thai-law/releases/download

fetch() {
  local tag=$1 name=$2 label=$3
  if [ -s "data/raw/$name" ]; then
    echo "มีอยู่แล้ว: data/raw/$name ($(wc -c <"data/raw/$name" | tr -d ' ') bytes)"
    return
  fi
  echo "==> ดาวน์โหลด $label"
  curl -fsSL -o "data/raw/$name" "$BASE/$tag/$name" || {
    echo "    ล้มเหลว ลองใหม่ที่ https://github.com/PyThaiNLP/thai-law/releases"
    return 1
  }
  echo "    $(wc -c <"data/raw/$name" | tr -d ' ') bytes"
}

fetch criminal-csv-v0.1 criminal-datasets.csv "ประมวลกฎหมายอาญา"
fetch civil-commercial-csv-v0.1 civil-and-commercial-datasets.csv "ประมวลกฎหมายแพ่งและพาณิชย์"

echo
echo "ต่อไป: python -m ingest.extract_acts   (จะผนวกประมวลเข้า corpus.jsonl ให้เอง)"
