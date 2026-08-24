# -*- coding: utf-8 -*-
"""Query embedding, either locally or through a hosted BGE-M3.

The index was built with sentence-transformers running BAAI/bge-m3 locally, and
that stays the way it is built. Serving is different: torch plus the model weighs
about 1.4 GB resident, which does not fit the 512 MB the target host gives us,
and loading it adds ~30 s to a cold start -- longer than a LINE reply token lives.

So the server calls a provider that hosts *the same checkpoint*. Same model means
the stored vectors remain valid and nothing about retrieval quality changes; the
parity check in tests/test_embed_parity.py is what holds that claim up.

Set `embed_backend=api` plus `embed_api_key` to use the remote path. With the
default `local`, this module is a thin wrapper over sentence-transformers and the
ingest pipeline keeps working unchanged.
"""
from __future__ import annotations

import logging

import httpx
import numpy as np

from app.config import settings

log = logging.getLogger(__name__)


class LocalEmbedder:
    """sentence-transformers on CPU.

    CPU, deliberately: BGE-M3 on Apple's MPS backend returns a silently wrong
    vector when a batch holds a single short sequence -- cosine against the CPU
    result drops to ~0.3 for some queries. Batched encoding is unaffected, which
    is why the index is fine and only query time was ever broken.
    """

    def __init__(self):
        self.model = None

    def encode(self, text: str) -> np.ndarray:
        if self.model is None:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(settings.embed_model, device="cpu")
        return self.model.encode([text], normalize_embeddings=True,
                                 convert_to_numpy=True)[0].astype(np.float32)


class ApiEmbedder:
    """A hosted BGE-M3 behind an OpenAI-compatible /embeddings endpoint."""

    def __init__(self):
        missing = [name for name, value in
                   (("embed_api_key", settings.embed_api_key),
                    ("embed_base_url", settings.embed_base_url))
                   if not value]
        if missing:
            raise RuntimeError(
                f"embed_backend=api but {' and '.join(missing)} empty -- set in .env")
        self._client = httpx.Client(
            base_url=settings.embed_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.embed_api_key}"},
            timeout=settings.embed_timeout)

    def encode(self, text: str) -> np.ndarray:
        resp = self._client.post("/embeddings",
                                 json={"model": settings.embed_api_model,
                                       "input": [text],
                                       "encoding_format": "float"})
        resp.raise_for_status()
        vec = np.asarray(resp.json()["data"][0]["embedding"], dtype=np.float32)
        # providers differ on whether they return a normalised vector, and the
        # stored index is normalised, so cosine is only a dot product if this is
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec


def get_embedder():
    if settings.embed_backend == "api":
        log.info("embeddings: %s via %s", settings.embed_api_model,
                 settings.embed_base_url)
        return ApiEmbedder()
    log.info("embeddings: %s local on CPU", settings.embed_model)
    return LocalEmbedder()
