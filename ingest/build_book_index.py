# -*- coding: utf-8 -*-
"""Build the index of the textbook corpus.

  data/processed/corpus_network.jsonl
      -> data/index/network_vectors.npy
         data/index/network_bm25_compact.npz, network_bm25_vocab.json

Run after ingest.extract_book, then ingest.calibrate_book: the gate in
app/config.py (`book_min_sim`) was read off these vectors.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings  # noqa: E402
from ingest.build_bm25_compact import write_compact  # noqa: E402


def embed_text(rec: dict) -> str:
    """The chapter and the section go in front of every chunk.

    Step 7 of a procedure reads "คลิกปุ่ม OK" and nothing else; which procedure
    it belongs to is only in the heading above it.
    """
    head = f"บทที่ {rec['chapter']} {rec['chapter_title']}"
    if rec.get("heading"):
        head += f" — {rec['heading']}"
    return f"{head}\n{rec['text']}"


def main() -> None:
    if not os.path.exists(settings.book_path):
        raise SystemExit(f"ไม่พบ {settings.book_path} "
                         "รัน python -m ingest.extract_book ก่อน")
    with open(settings.book_path, encoding="utf-8") as handle:
        corpus = [json.loads(line) for line in handle]
    if not corpus:
        raise SystemExit(f"{settings.book_path} ว่างเปล่า")
    texts = [embed_text(r) for r in corpus]
    print(f"book: {len(corpus):,} chunks")

    from app.thai_tokenize import word_tokenize
    from rank_bm25 import BM25Okapi
    bm25 = BM25Okapi([word_tokenize(t, keep_whitespace=False) for t in texts])
    size = write_compact(bm25, settings.book_bm25_path, settings.book_vocab_path)
    print(f"-> {settings.book_bm25_path} ({size:.1f} MB)")

    from sentence_transformers import SentenceTransformer
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"loading {settings.embed_model} on {device} ...")
    model = SentenceTransformer(settings.embed_model, device=device)
    t0 = time.time()
    vecs = model.encode(texts, batch_size=16, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True)
    np.save(settings.book_vectors_path, vecs.astype(np.float16))
    print(f"encoded in {time.time() - t0:.0f}s -> {settings.book_vectors_path} "
          f"{vecs.shape}")
    print("ต่อไป: python -m ingest.calibrate_book")


if __name__ == "__main__":
    main()
