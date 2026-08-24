# -*- coding: utf-8 -*-
"""Signature verification is the only thing standing between the webhook and the
open internet, so it gets tested even though no LINE channel exists yet."""
import base64
import hashlib
import hmac

from app import line_bot
from app.config import settings

SECRET = "test-channel-secret"
BODY = b'{"events":[{"type":"message"}]}'


def sign(body: bytes, secret: str) -> str:
    return base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_accepts_a_correct_signature(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    assert line_bot.verify_signature(BODY, sign(BODY, SECRET))


def test_rejects_a_wrong_signature(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    assert not line_bot.verify_signature(BODY, sign(BODY, "other-secret"))


def test_rejects_a_tampered_body(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    assert not line_bot.verify_signature(b'{"events":[]}', sign(BODY, SECRET))


def test_rejects_when_no_secret_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", "")
    assert not line_bot.verify_signature(BODY, sign(BODY, SECRET))


def test_rejects_an_empty_signature(monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    assert not line_bot.verify_signature(BODY, "")
