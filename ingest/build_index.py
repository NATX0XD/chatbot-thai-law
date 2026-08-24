# -*- coding: utf-8 -*-
"""Build both halves of the hybrid index from data/corpus.jsonl.

Dense: BGE-M3 embeddings, L2-normalised, stored as one float16 matrix so the whole
index fits in memory (33k x 1024 x 2 bytes = 68 MB) and cosine similarity is a
single matmul -- no vector database needed at this scale.

Sparse: BM25 over pythainlp word tokens. This half is what makes "มาตรา 118" and
"ค่าชดเชย" hit exactly; dense retrieval alone reliably misses literal section numbers.

    python -m ingest.build_index            # both
    python -m ingest.build_index --bm25     # sparse only (fast, no torch)
"""
import argparse
import json
import os
import pickle
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings  # noqa: E402


def load_corpus():
    with open(settings.corpus_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def embed_text(rec):
    """Prefix each chunk with its act and section so short sections stay findable.

    A section like "ปีบัญชีของกองทุนหมายถึงปีงบประมาณ" is meaningless on its own;
    with the act name attached it still answers "ปีบัญชีของกองทุน X คืออะไร".
    """
    return f"{rec['act']} มาตรา {rec['section']}\n{rec['text']}"


def build_dense(corpus):
    from sentence_transformers import SentenceTransformer
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"loading {settings.embed_model} on {device} ...")
    model = SentenceTransformer(settings.embed_model, device=device)

    texts = [embed_text(r) for r in corpus]
    t0 = time.time()
    vecs = model.encode(texts, batch_size=16, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True)
    print(f"encoded {len(texts):,} chunks in {time.time() - t0:.0f}s -> {vecs.shape}")
    np.save(settings.vectors_path, vecs.astype(np.float16))
    print(f"-> {settings.vectors_path} ({os.path.getsize(settings.vectors_path) / 1e6:.0f} MB)")


def build_bm25(corpus):
    # the vendored newmm, not pythainlp's, so that the tokens fitted here are by
    # construction the tokens the server will produce -- upgrading pythainlp on a
    # workstation would otherwise silently shift the query side away from the index
    from app.thai_tokenize import word_tokenize
    from rank_bm25 import BM25Okapi

    t0 = time.time()
    tokens = [word_tokenize(embed_text(r), keep_whitespace=False) for r in corpus]
    print(f"tokenised {len(tokens):,} chunks in {time.time() - t0:.0f}s")
    bm25 = BM25Okapi(tokens)
    with open(settings.bm25_path, "wb") as f:
        pickle.dump(bm25, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"-> {settings.bm25_path} ({os.path.getsize(settings.bm25_path) / 1e6:.0f} MB)")

    # chained on purpose: the compact index is what the retriever actually loads,
    # so leaving it as a separate command to remember means the next rebuild
    # serves the previous corpus
    from ingest.build_bm25_compact import main as compact
    compact()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bm25", action="store_true", help="build the sparse index only")
    ap.add_argument("--dense", action="store_true", help="build the dense index only")
    args = ap.parse_args()

    corpus = load_corpus()
    print(f"corpus: {len(corpus):,} chunks")
    both = not (args.bm25 or args.dense)
    if both or args.bm25:
        build_bm25(corpus)
    if both or args.dense:
        build_dense(corpus)


if __name__ == "__main__":
    main()
