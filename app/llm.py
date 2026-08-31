# -*- coding: utf-8 -*-
"""The writing step, with more than one provider behind it.

Typhoon and Gemini both speak the OpenAI protocol, so one SDK with two base URLs
covers both and switching providers is a config change rather than a rewrite.

The chain is Typhoon 30B, then Typhoon 12B, then Gemini. Typhoon leads because
it is the Thai model the prompt and the answer format were tuned against; the
12B has separate rate-limit headroom; Gemini is there because Typhoon's own
documentation calls the free API a research showcase that is rate limited and
not intended for high-throughput use.

What the extra provider does *not* change is what the bot will say. Every model
in the chain gets the same system prompt and the same retrieved sections, and
every answer goes through app/verify.py afterwards. A second provider buys
availability, not a second opinion on the law.
"""
from __future__ import annotations

import logging

from openai import APIStatusError, AsyncOpenAI, RateLimitError

from app.config import settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when every model we are willing to try has failed."""


_clients: dict[str, AsyncOpenAI] = {}


def _client(provider: str) -> AsyncOpenAI:
    if provider not in _clients:
        key, base = ((settings.gemini_api_key, settings.gemini_base_url)
                     if provider == "gemini"
                     else (settings.typhoon_api_key, settings.typhoon_base_url))
        _clients[provider] = AsyncOpenAI(api_key=key, base_url=base,
                                         timeout=settings.llm_timeout)
    return _clients[provider]


def _chain() -> list[tuple[str, str]]:
    """(provider, model) in the order they are tried.

    Typhoon first because it is the Thai model the answers were tuned against.
    Gemini last and only if configured -- it writes from the same retrieved
    sections under the same system prompt, and its output goes through the same
    citation check, so adding it widens availability without widening what the
    bot is willing to claim.
    """
    chain = [("typhoon", settings.typhoon_model),
             ("typhoon", settings.typhoon_fallback_model)]
    if settings.gemini_api_key:
        chain.append(("gemini", settings.gemini_model))
    return chain


async def complete(system: str, user: str) -> str:
    chain = _chain()
    if not settings.typhoon_api_key and not settings.gemini_api_key:
        raise LLMUnavailable(
            "ยังไม่ได้ตั้งค่า TYPHOON_API_KEY หรือ GEMINI_API_KEY — "
            "ขอคีย์ฟรีที่ https://opentyphoon.ai หรือ https://aistudio.google.com/apikey")

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    last_error: Exception | None = None
    for provider, model in chain:
        if provider == "typhoon" and not settings.typhoon_api_key:
            continue
        try:
            resp = await _client(provider).chat.completions.create(
                model=model,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                return text
            # an empty body is a failure like any other; falling through keeps a
            # blank bubble from reaching the user when another provider is ready
            log.warning("%s %s returned nothing, falling back", provider, model)
            last_error = RuntimeError(f"{provider} {model} returned an empty answer")
        except RateLimitError as exc:
            log.warning("%s %s rate limited, falling back", provider, model)
            last_error = exc
        except APIStatusError as exc:
            log.warning("%s %s failed: %s", provider, model, exc.status_code)
            last_error = exc

    raise LLMUnavailable(f"เรียกโมเดลไม่สำเร็จทุกตัว: {last_error}") from last_error
