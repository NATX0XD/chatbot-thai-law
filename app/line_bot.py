# -*- coding: utf-8 -*-
"""LINE Messaging API integration, written against the raw HTTP API.

Deliberately no `line-bot-sdk` dependency: we need exactly three calls (verify a
signature, reply, show a loading animation) and the SDK's sync client would have
to be bridged into the async request path anyway.

Timing constraint that shapes this module: LINE expects the webhook to return
200 within a few seconds, and a reply token expires in about 30 seconds. RAG plus
Typhoon takes longer than the first budget and sometimes approaches the second, so
the webhook acknowledges immediately and answers from a background task, falling
back to the push API if the reply token has gone stale.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re

import httpx

from app.answer import answer_question
from app.config import settings
# one wording for the welcome text, shared with the 'สวัสดี' path
from app.smalltalk import CAPABILITIES, GREETING

log = logging.getLogger(__name__)

GROUP_GREETING = (
    "สวัสดีครับ ขอบคุณที่ชวนเข้ากลุ่ม 🙏\n\n"
    "ในกลุ่มผมจะเงียบไว้ ไม่แทรกทุกข้อความ เรียกใช้ได้ 2 วิธี\n"
    "1. พิมพ์ @ แล้วเลือกชื่อผม ตามด้วยคำถาม\n"
    "2. ขึ้นต้นข้อความด้วยคำว่า กฎหมาย เช่น\n"
    "   กฎหมาย ลาออกต้องบอกล่วงหน้ากี่วัน\n\n"
    + CAPABILITIES
)

# In a one-to-one chat every message is meant for the bot. In a group it is not:
# LINE delivers every message posted there, so answering all of them would make
# the bot unusable. It speaks only when addressed.
GROUP_TRIGGER = re.compile(r"^\s*(กฎหมาย|บอท|bot)\s*[:：]?\s*", re.I)


def chat_target(source: dict) -> str | None:
    """Where a message came from -- group, multi-person room, or a single user.

    Loading indicators and push messages address the *conversation*, not the
    sender, so a group reply must go to the groupId. Using userId here would send
    the answer to the asker's private chat instead of back to the group.
    """
    return source.get("groupId") or source.get("roomId") or source.get("userId")


def strip_mention(message: dict, text: str) -> tuple[str, bool]:
    """Remove an @-mention of this bot and report whether one was present."""
    mentioned = False
    spans = []
    for m in (message.get("mention") or {}).get("mentionees", []):
        # isSelf marks a mention of this bot; older payloads only carry userId
        if m.get("isSelf") or (settings.line_bot_user_id
                               and m.get("userId") == settings.line_bot_user_id):
            mentioned = True
            spans.append((m.get("index", 0), m.get("length", 0)))
    for start, length in sorted(spans, reverse=True):
        text = text[:start] + text[start + length:]
    return text.strip(), mentioned


REPLY_URL = "https://api.line.me/v2/bot/message/reply"
PUSH_URL = "https://api.line.me/v2/bot/message/push"
LOADING_URL = "https://api.line.me/v2/bot/chat/loading/start"



def verify_signature(body: bytes, signature: str) -> bool:
    """LINE signs every webhook body with the channel secret; unsigned = not LINE."""
    if not settings.line_channel_secret or not signature:
        return False
    digest = hmac.new(settings.line_channel_secret.encode("utf-8"), body,
                      hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode("utf-8"), signature)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.line_channel_access_token}",
            "Content-Type": "application/json"}


async def show_loading(chat_id: str, seconds: int = 60) -> None:
    """The typing indicator; purely cosmetic, so failures are swallowed."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(LOADING_URL, headers=_headers(),
                              json={"chatId": chat_id,
                                    "loadingSeconds": min(seconds, 60)})
    except httpx.HTTPError as exc:
        log.debug("loading indicator failed: %s", exc)


def _as_messages(payload) -> list[dict]:
    """Accept a string, one message dict, or a list. LINE caps a send at 5."""
    if isinstance(payload, str):
        payload = [{"type": "text", "text": payload}]
    elif isinstance(payload, dict):
        payload = [payload]
    return list(payload)[:5]


async def reply(reply_token: str, payload) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(REPLY_URL, headers=_headers(),
                                 json={"replyToken": reply_token,
                                       "messages": _as_messages(payload)})
    if resp.status_code != 200:
        log.warning("reply failed %s: %s", resp.status_code, resp.text[:300])
    return resp.status_code == 200


async def push(to: str, payload) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(PUSH_URL, headers=_headers(),
                                 json={"to": to, "messages": _as_messages(payload)})
    if resp.status_code != 200:
        log.warning("push failed %s: %s", resp.status_code, resp.text[:300])
    return resp.status_code == 200


async def handle_event(event: dict) -> None:
    """Answer one webhook event. Runs detached from the webhook response."""
    etype = event.get("type")
    source = event.get("source", {})
    in_group = source.get("type") in ("group", "room")
    target = chat_target(source)
    reply_token = event.get("replyToken")

    # added as a friend, or invited into a group
    if etype in ("follow", "join"):
        if reply_token:
            await reply(reply_token, GROUP_GREETING if etype == "join" else GREETING)
        return

    if etype != "message" or event.get("message", {}).get("type") != "text":
        return

    text = event["message"]["text"].strip()

    if in_group:
        text, mentioned = strip_mention(event["message"], text)
        triggered = GROUP_TRIGGER.match(text)
        if not (mentioned or triggered):
            return  # not addressed to the bot; stay quiet
        if triggered:
            text = GROUP_TRIGGER.sub("", text, count=1).strip()
        if not text:
            if reply_token:
                await reply(reply_token, GROUP_GREETING)
            return
        log.info("GROUP %s | %r", "mention" if mentioned else "keyword", text[:60])

    if target:
        await show_loading(target)

    try:
        answer = await answer_question(text)
        body = answer.for_line_messages()
    except Exception:
        log.exception("failed to answer %r", text[:80])
        body = "ขออภัยครับ ระบบขัดข้องชั่วคราว ลองถามใหม่อีกครั้งได้เลย"

    sent = await reply(reply_token, body) if reply_token else False
    if not sent and target:
        await push(target, body)
