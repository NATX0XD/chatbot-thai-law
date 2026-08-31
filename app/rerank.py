# -*- coding: utf-8 -*-
"""Cross-encoder reranking through Cloudflare Workers AI.

Fusion orders results without ever comparing the question to a section directly:
the dense side compares two vectors that were produced independently, and BM25
counts word overlap. Neither can answer "does this section actually answer this
question", which is why a question about returning an online purchase can surface
พ.ร.บ.ชดเชยค่าภาษีอากรสินค้าส่งออก above the cosine gate.

A cross-encoder reads the question and the section together in one pass and
scores the pair, which is the question that matters. It is also slower by roughly
the same amount, so this stage is off by default and switched on only if measured
to help -- see ingest/eval_retrieval.py --rerank.

The only reranker on Workers AI is @cf/baai/bge-reranker-base, which is trained
mainly on English and Chinese. Whether it holds up on Thai statute text is an
empirical question, not an assumption; a first probe put ประมวลกฎหมายอาญา ม.335
above a labour-law section for a labour question, which is why nothing is wired
into the serving path until the numbers say so.
"""
from __future__ import annotations

import logging
import re

import httpx

from app.config import settings

log = logging.getLogger(__name__)

# the embeddings base URL is the OpenAI-compatible shim; the reranker is only
# exposed on the native path, so the account id is lifted out of the one we have
ACCOUNT_RE = re.compile(r"/accounts/([^/]+)/")

# bge-reranker-base takes 512 tokens of context. Thai runs roughly 2-3 characters
# per token, so a 1,800-character chunk would be cut off mid-way by the provider
# with no warning. Truncating here makes the cut explicit and keeps the opening
# of the section, which is where the rule itself is stated.
MAX_PASSAGE_CHARS = 900


class Reranker:
    """Scores (question, section) pairs with a cross-encoder."""

    def __init__(self):
        match = ACCOUNT_RE.search(settings.embed_base_url or "")
        if not match or not settings.embed_api_key:
            raise RuntimeError(
                "rerank needs embed_base_url (.../accounts/<id>/ai/v1) and "
                "embed_api_key -- set them in .env")
        self.url = (f"https://api.cloudflare.com/client/v4/accounts/"
                    f"{match.group(1)}/ai/run/{settings.rerank_model}")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {settings.embed_api_key}"},
            timeout=settings.rerank_timeout)

    def order(self, question: str, passages: list[str]) -> list[int]:
        """Return indexes of `passages`, best first.

        On any failure the original order is returned unchanged. A reranker is an
        improvement to ordering, not a dependency: losing it should cost quality,
        never an answer.
        """
        if not passages:
            return []
        body = {"query": question,
                "contexts": [{"text": p[:MAX_PASSAGE_CHARS]} for p in passages]}
        try:
            resp = self._client.post(self.url, json=body)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("rerank failed, keeping fusion order: %s", exc)
            return list(range(len(passages)))

        if not data.get("success"):
            log.warning("rerank returned an error, keeping fusion order: %s",
                        str(data.get("errors"))[:200])
            return list(range(len(passages)))

        ranked = data["result"]["response"]
        order = [int(item["id"]) for item in ranked if 0 <= item["id"] < len(passages)]
        # the provider is expected to return every context; if it returns fewer,
        # the ones it dropped keep their fused position at the end rather than
        # disappearing from the answer entirely
        seen = set(order)
        order += [i for i in range(len(passages)) if i not in seen]
        return order


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
