# Serving image for the Thai law chatbot.
#
# Everything about it is shaped by a 512 MB memory ceiling: no torch, no
# rank_bm25, no pythainlp, a memory-mapped vector index and a corpus read by byte
# offset. See requirements-server.txt for why each of those is gone.
#
# The index is copied in, not built here: building the dense index needs the
# 2.2 GB BGE-M3 checkpoint and takes ~18 minutes, which belongs on a workstation.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY app/ app/
COPY web/ web/

# only the three files the retriever opens; data/raw and the intermediate
# processed artefacts stay out of the image
COPY data/processed/corpus.jsonl        data/processed/corpus.jsonl
COPY data/index/vectors.npy             data/index/vectors.npy
COPY data/index/bm25_compact.npz        data/index/bm25_compact.npz
COPY data/index/bm25_vocab.json         data/index/bm25_vocab.json

# the remote embedder is the whole point of this image; leaving the default
# would make it try to import torch at the first question
ENV EMBED_BACKEND=api

EXPOSE 8000

# one worker on purpose: a second would load its own copy of the index and
# double the memory, and the workload is I/O-bound on two upstream APIs anyway.
# Render supplies $PORT; the default keeps `docker run -p 8000:8000` working.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
