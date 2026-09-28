# -*- coding: utf-8 -*-
"""A short in-memory record of recent chat traffic, for watching the bot live.

Render's log tail already shows every inbound message once line_bot logs it, but a
log tail is a browser tab that has to stay open and cannot be polled from a phone
or from Postman. This keeps the last few exchanges in memory so /recent can return
them as JSON.

In memory on purpose. The free instance restarts on deploy and sleeps after
fifteen idle minutes, so anything here is already temporary; writing it to disk
would turn a debugging aid into a store of other people's messages with no
retention policy and no way to honour a deletion request.

The LINE userId is never kept. It is replaced by a short hash, plus a "คนที่ N"
label handed out in the order people first appear, so a conversation can be
followed and two people told apart without the raw id being readable by whoever
holds the monitor token.

The question and the answer are both kept, truncated. Watching only the questions
does not tell you whether the bot is doing its job, which is the whole reason for
looking.
"""
from __future__ import annotations

import collections
import hashlib
import time
from typing import Deque

# Roughly the last hour of a quiet demo. Small enough that the whole buffer fits
# in one response without paging.
CAPACITY = 100

# Long enough for a full answer with its citations; the LINE reply itself is
# capped at 1,800 characters upstream.
MAX_ANSWER = 2000

_events: Deque[dict] = collections.deque(maxlen=CAPACITY)

# hashed id -> "คนที่ N", in order of first message. Cleared on restart along
# with the buffer, so the numbering always matches what /recent is showing.
_people: dict[str, str] = {}


def short_id(user_id: str) -> str:
    """Stable eight-character stand-in for a LINE userId."""
    if not user_id:
        return "-"
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


def label(user_id: str) -> str:
    """"คนที่ 1", "คนที่ 2", ... assigned on first sight."""
    if not user_id:
        return "หน้าเว็บ"
    key = short_id(user_id)
    if key not in _people:
        _people[key] = f"คนที่ {len(_people) + 1}"
    return _people[key]


def record(*, source: str, user: str, text: str, **extra) -> dict:
    """Append one inbound message. Returns the entry so the caller can finish it."""
    entry = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "epoch": time.time(),
        "source": source,          # "user", "group" or "web"
        "who": label(user),
        "user": short_id(user),
        "question": text[:400],
        "answer": None,            # filled in by finish()
        "answered": None,
        **extra,
    }
    _events.append(entry)
    return entry


def finish(entry: dict, *, answer: str | None = None, in_scope: bool | None = None,
           faults=None, repair=None, error: str | None = None) -> None:
    """Fill in the reply and the outcome once the answer is ready."""
    entry["answered"] = round(time.time() - entry["epoch"], 1)
    entry["answer"] = (answer or "")[:MAX_ANSWER] or None
    entry["in_scope"] = in_scope
    entry["faults"] = faults or []
    entry["repair"] = repair
    if error:
        entry["error"] = error


def recent(limit: int = 50) -> list[dict]:
    """Newest first."""
    return list(_events)[-limit:][::-1]


def summary() -> dict:
    events = list(_events)
    answered = [e for e in events if e.get("answered") is not None]
    return {
        "kept": len(events),
        "capacity": CAPACITY,
        "people": len({e["who"] for e in events if e["who"] != "หน้าเว็บ"}),
        "last_at": events[-1]["at"] if events else None,
        "refused": sum(1 for e in events if e.get("in_scope") is False),
        "errors": sum(1 for e in events if e.get("error")),
        "mean_seconds": (round(sum(e["answered"] for e in answered) / len(answered), 1)
                         if answered else None),
    }
