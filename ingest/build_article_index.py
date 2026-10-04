# -*- coding: utf-8 -*-
"""Build the dense and sparse index over data/processed/corpus_articles.jsonl.

The same two halves as ingest/build_index.py -- BGE-M3 vectors and BM25 over
newmm tokens -- written to their own files, so rebuilding the articles can never
disturb the index the measured answers were produced with.

    python -m ingest.build_article_index
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings  # noqa: E402
from ingest.build_bm25_compact import write_compact  # noqa: E402


def embed_text(rec: dict) -> str:
    """The title and the heading go in front of every chunk.

    A paragraph from the middle of วิธีดำเนินการวิจัย does not say which study
    it belongs to; the question "บทความเรื่องไตรสิกขาเก็บข้อมูลจากใคร" does.
    """
    head = rec["title"] + (f" — {rec['heading']}" if rec.get("heading") else "")
    return f"{head}\n{rec['text']}"


def main() -> None:
    if not os.path.exists(settings.articles_path):
        raise SystemExit(f"ไม่พบ {settings.articles_path} "
                         "รัน python -m ingest.extract_articles ก่อน")
    with open(settings.articles_path, encoding="utf-8") as handle:
        corpus = [json.loads(line) for line in handle]
    if not corpus:
        raise SystemExit(f"{settings.articles_path} ว่างเปล่า")
    texts = [embed_text(r) for r in corpus]
    print(f"articles: {len(corpus):,} chunks")

    from app.thai_tokenize import word_tokenize
    from rank_bm25 import BM25Okapi
    bm25 = BM25Okapi([word_tokenize(t, keep_whitespace=False) for t in texts])
    size = write_compact(bm25, settings.articles_bm25_path, settings.articles_vocab_path)
    print(f"-> {settings.articles_bm25_path} ({size:.1f} MB)")

    from sentence_transformers import SentenceTransformer
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"loading {settings.embed_model} on {device} ...")
    model = SentenceTransformer(settings.embed_model, device=device)
    t0 = time.time()
    vecs = model.encode(texts, batch_size=16, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True)
    np.save(settings.articles_vectors_path, vecs.astype(np.float16))
    print(f"encoded in {time.time() - t0:.0f}s -> {settings.articles_vectors_path} "
          f"{vecs.shape}")


if __name__ == "__main__":
    main()
