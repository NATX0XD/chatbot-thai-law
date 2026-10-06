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

from app import line_bot, monitor
from app import articles, book
from app.answer import answer_question
from app.config import BASE_DIR, settings
from app.retriever import get_retriever

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("network-basics-bot")

WEB_DIR = os.path.join(BASE_DIR, "web")
app = FastAPI(title="KMUTNB Network Basics Chatbot", version="0.2.0")


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
    if settings.dataset == "network":
        index = await asyncio.to_thread(book.get_index)
        try:
            await asyncio.to_thread(index.find, "อุ่นเครื่อง")
            warm = "warm"
        except Exception as exc:
            log.warning("warm-up query failed, serving anyway: %s", exc)
            warm = "cold"
        log.info("book ready: %d chunks in %.1fs (embedder %s)",
                 len(index.corpus), time.time() - t0, warm)
        return
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
    if settings.dataset == "network":
        index = book.get_index()
        return {
            "status": "ok",
            "dataset": "network",
            "chunks": len(index.corpus),
            "dense_index": True,
            "figures": len(index.figures),
            "step_photos": sum(len(v) for v in index.photos.values()),
            "llm_configured": bool(settings.typhoon_api_key),
            "line_configured": bool(settings.line_channel_secret
                                    and settings.line_channel_access_token),
        }
    r = get_retriever()
    return {
        "status": "ok",
        "chunks": len(r.corpus),
        "dense_index": r.vectors is not None,
        # the journal-article fallback; false means rules only
        "articles": articles.get_index() is not None,
        "llm_configured": bool(settings.typhoon_api_key),
        "line_configured": bool(settings.line_channel_secret
                                and settings.line_channel_access_token),
        "corpus_as_of": settings.corpus_as_of,
    }


_STATS: dict | None = None


@app.get("/stats")
async def stats() -> dict:
    """What the corpus actually contains, for the UI to state instead of guess.

    Computed by streaming the corpus once and keeping only counters -- the store
    parses a line at a time and drops it, so this costs a file read rather than
    the 97 MB that holding every record would. Cached, because the corpus is
    read-only for the life of the process.
    """
    global _STATS
    if _STATS is None and settings.dataset == "network":
        def chapters() -> dict:
            index = book.get_index()
            per: dict[int, dict] = {}
            for rec in index.corpus:
                row = per.setdefault(rec["chapter"], {
                    "chapter": rec["chapter"], "title": rec["chapter_title"],
                    "sections": set(), "chunks": 0})
                row["chunks"] += 1
                if rec.get("heading"):
                    row["sections"].add(rec["heading"])
            listing = [{**row, "sections": len(row["sections"])}
                       for _, row in sorted(per.items())]
            return {"dataset": "network", "book": book.BOOK,
                    "chapters": len(listing),
                    "sections": sum(r["sections"] for r in listing),
                    "chunks": len(index.corpus), "figures": len(index.figures),
                    "largest": listing}
        _STATS = await asyncio.to_thread(chapters)
    if _STATS is None:
        def build() -> dict:
            corpus = get_retriever().corpus
            per_act: dict[str, set] = {}
            for rec in corpus:
                # long sections are split into parts; count the section once
                per_act.setdefault(rec["act"], set()).add(rec["section"])
            top = sorted(per_act.items(), key=lambda kv: -len(kv[1]))[:12]
            return {
                "acts": len(per_act),
                "sections": sum(len(v) for v in per_act.values()),
                "chunks": len(corpus),
                "corpus_as_of": settings.corpus_as_of,
                "largest": [{"act": a, "sections": len(s)} for a, s in top],
            }
        _STATS = await asyncio.to_thread(build)
    return _STATS


# ----------------------------------------------------------------- web chat

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    # The web page and LINE share one buffer, so /recent shows the whole of what
    # the bot is being asked, not just the half that arrived over LINE.
    entry = monitor.record(source="web", user="", text=req.question)
    answer = await answer_question(req.question)
    monitor.finish(entry, answer=answer.text, in_scope=answer.in_scope,
                   faults=answer.faults, repair=answer.repair, error=answer.error)
    return {
        "answer": answer.text,
        "in_scope": answer.in_scope,
        # "rules" or "articles": which corpus the answer was written from
        "source": answer.source,
        # pictures from the textbook that belong under this answer
        "figures": answer.figures,
        "error": answer.error,
        # what the guards found on the first draft, and whether the rewrite was
        # accepted. For reading acceptance runs without diffing against the
        # previous one.
        "faults": answer.faults,
        "repair": answer.repair,
        "sources": [
            {"citation": h.citation, "score": round(h.rrf, 4),
             "dense": round(h.dense_score, 4), "bm25": round(h.bm25_score, 3),
             "dense_rank": h.dense_rank, "bm25_rank": h.bm25_rank,
             "text": h.rec["text"]}
            for h in answer.hits
        ],
    }


@app.get("/recent")
async def recent(token: str = "", limit: int = 50) -> dict:
    """What people have just asked, newest first. Poll this to watch the bot live.

    Off unless MONITOR_TOKEN is set, and 404 rather than 403 when it is missing or
    wrong: an endpoint that answers "wrong token" tells a stranger that questions
    are there to be read.
    """
    if not settings.monitor_token or token != settings.monitor_token:
        raise HTTPException(404, "Not Found")
    return {"summary": monitor.summary(),
            "events": monitor.recent(max(1, min(limit, monitor.CAPACITY)))}


@app.get("/search")
async def search(q: str, k: int = 6) -> dict:
    """Retrieval only -- tune the in-scope thresholds without spending LLM calls."""
    if settings.dataset == "network":
        hits, best = await asyncio.to_thread(book.get_index().find, q, k)
        return {
            "query": q,
            "in_scope": best >= settings.book_min_sim,
            "max_dense": round(best, 4),
            "hits": [{"citation": h.citation, "rrf": round(h.rrf, 4),
                      "dense": round(h.dense_score, 4), "bm25": round(h.bm25_score, 3),
                      "dense_rank": h.dense_rank, "bm25_rank": h.bm25_rank,
                      "figures": h.rec.get("figures", []),
                      "text": h.rec["text"][:500]} for h in hits],
        }
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
        # index.html is the networking bot's page; the Teachers Council page
        # is kept beside it and served when DATASET=ksp
        page = "index.html" if settings.dataset == "network" else "index_ksp.html"
        return FileResponse(os.path.join(WEB_DIR, page))
