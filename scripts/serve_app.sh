#!/usr/bin/env bash
# Run the FastAPI app in the foreground so launchd owns the process and restarts
# it on crash. Index building is left out on purpose: it takes tens of minutes and
# a supervised service must not silently start a long job on every restart.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
PY=.venv/bin/python
[ -x "$PY" ] || { echo "missing .venv -- see README"; exit 1; }

for f in data/processed/corpus.jsonl data/index/bm25.pkl data/index/vectors.npy; do
  [ -f "$f" ] || { echo "missing $f -- run: $PY -m ingest.extract_acts && $PY -m ingest.build_index"; exit 1; }
done

exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
