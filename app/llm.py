# -*- coding: utf-8 -*-
"""Typhoon client. The Typhoon API speaks the OpenAI protocol, so the official
OpenAI SDK is used with a different base_url -- no bespoke HTTP code needed.

Typhoon's free tier is rate limited and returns 429 under load; on 429 or on a
model-level failure we retry once against the smaller model, which has separate
headroom, before giving up.
"""
from __future__ import annotations

import logging

from openai import APIStatusError, AsyncOpenAI, RateLimitError

from app.config import settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when every model we are willing to try has failed."""


_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.typhoon_api_key:
            raise LLMUnavailable(
                "ยังไม่ได้ตั้งค่า TYPHOON_API_KEY — ขอคีย์ฟรีที่ https://opentyphoon.ai")
        _client = AsyncOpenAI(api_key=settings.typhoon_api_key,
                              base_url=settings.typhoon_base_url,
                              timeout=settings.llm_timeout)
    return _client


async def complete(system: str, user: str) -> str:
    client = get_client()
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    last_error: Exception | None = None
    for model in (settings.typhoon_model, settings.typhoon_fallback_model):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except RateLimitError as exc:
            log.warning("typhoon %s rate limited, falling back", model)
            last_error = exc
        except APIStatusError as exc:
            log.warning("typhoon %s failed: %s", model, exc.status_code)
            last_error = exc

    raise LLMUnavailable(f"เรียก Typhoon ไม่สำเร็จ: {last_error}") from last_error
