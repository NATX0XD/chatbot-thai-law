#!/usr/bin/env bash
# Start the chatbot, building whatever part of the index is missing first.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
[ -x "$PY" ] || { echo "ยังไม่มี venv — รัน: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
[ -f .env ] || { cp .env.example .env; echo "สร้าง .env จาก .env.example แล้ว — ใส่ TYPHOON_API_KEY ก่อนใช้งานจริง"; }

[ -f data/corpus.jsonl ] || { echo "==> สกัดตัวบท"; $PY -m ingest.extract_acts; }
[ -f data/bm25.pkl ]     || { echo "==> สร้างดัชนี BM25"; $PY -m ingest.build_index --bm25; }
[ -f data/vectors.npy ]  || { echo "==> สร้างดัชนีเชิงความหมาย (ครั้งแรกโหลดโมเดล 2.2 GB)"; $PY -m ingest.build_index --dense; }

echo "==> http://localhost:${PORT:-8000}"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
