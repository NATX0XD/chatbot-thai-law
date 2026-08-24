# -*- coding: utf-8 -*-
"""FastAPI app: LINE webhook plus a plain web chat for testing without a channel."""
from __future__ import annotations

import asyncio
import logging
import os
import time

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import line_bot
from app.answer import answer_question
from app.config import BASE_DIR, settings
from app.retriever import get_retriever

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("law-chatbot")

WEB_DIR = os.path.join(BASE_DIR, "web")
app = FastAPI(title="KMUTNB Thai Law Chatbot", version="0.1.0")


@app.on_event("startup")
async def warm_up() -> None:
    """Load the indexes and run one throwaway query at boot.

    The embedder is lazy, and paying for it on the first real question pushed
    seconds onto whoever asked it -- on LINE that is long enough to look broken.

    A missing index is fatal: the service cannot answer anything without it. A
    failing warm-up query is not, because the remote embedder is now a network
    call, and refusing to start over one bad response would turn a blip at the
    provider into a service that stays down until someone redeploys it.
    """
    t0 = time.time()
    r = await asyncio.to_thread(get_retriever)
    try:
        await asyncio.to_thread(r.search, "อุ่นเครื่อง")
        warm = "warm"
    except Exception as exc:
        log.warning("warm-up query failed, serving anyway: %s", exc)
        warm = "cold"
    log.info("index ready: %s chunks in %.1fs (dense=%s, embedder %s)",
             f"{len(r.corpus):,}", time.time() - t0, r.vectors is not None, warm)


@app.get("/health")
async def health() -> dict:
    r = get_retriever()
    return {
        "status": "ok",
        "chunks": len(r.corpus),
        "dense_index": r.vectors is not None,
        "llm_configured": bool(settings.typhoon_api_key),
        "line_configured": bool(settings.line_channel_secret
                                and settings.line_channel_access_token),
        "corpus_as_of": settings.corpus_as_of,
    }


# ----------------------------------------------------------------- web chat

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    answer = await answer_question(req.question)
    return {
        "answer": answer.text,
        "in_scope": answer.in_scope,
        "error": answer.error,
        "sources": [
            {"citation": h.citation, "score": round(h.rrf, 4),
             "dense": round(h.dense_score, 4), "bm25": round(h.bm25_score, 3),
             "dense_rank": h.dense_rank, "bm25_rank": h.bm25_rank,
             "text": h.rec["text"]}
            for h in answer.hits
        ],
    }


@app.get("/search")
async def search(q: str, k: int = 6) -> dict:
    """Retrieval only -- tune the in-scope thresholds without spending LLM calls."""
    res = await asyncio.to_thread(get_retriever().search, q, k)
    return {
        "query": q,
        "in_scope": res.in_scope,
        "max_dense": round(res.max_dense, 4),
        "max_bm25": round(res.max_bm25, 3),
        "exact_section": res.exact_section,
        "hits": [{"citation": h.citation, "rrf": round(h.rrf, 4),
                  "dense": round(h.dense_score, 4), "bm25": round(h.bm25_score, 3),
                  "dense_rank": h.dense_rank, "bm25_rank": h.bm25_rank,
                  "text": h.rec["text"][:500]} for h in res.hits],
    }


# ----------------------------------------------------------------- LINE

@app.post("/webhook")
async def line_webhook(request: Request, background: BackgroundTasks,
                       x_line_signature: str = Header(default="")):
    body = await request.body()

    if not settings.line_channel_secret:
        raise HTTPException(503, "ยังไม่ได้ตั้งค่า LINE_CHANNEL_SECRET")
    if not line_bot.verify_signature(body, x_line_signature):
        raise HTTPException(403, "invalid signature")

    payload = await request.json()
    for event in payload.get("events", []):
        background.add_task(line_bot.handle_event, event)

    # LINE retries on anything slower than a couple of seconds, so answer now and
    # let the background task deliver the reply
    return JSONResponse({"ok": True})


# ----------------------------------------------------------------- static

if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(os.path.join(WEB_DIR, "index.html"))
