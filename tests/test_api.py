# -*- coding: utf-8 -*-
"""HTTP surface tests. The webhook ones matter most: that route is reachable from
the open internet the moment the tunnel goes up."""
import base64
import hashlib
import hmac
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings

pytestmark = pytest.mark.skipif(
    not os.path.exists(settings.bm25_path),
    reason="index not built -- run ingest.extract_acts then ingest.build_index",
)

SECRET = "test-channel-secret"
EVENT = {"events": [{"type": "message", "replyToken": "rt",
                     "source": {"userId": "u1"},
                     "message": {"type": "text", "text": "สวัสดี"}}]}


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_health_reports_index_state(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["chunks"] > 20000
    assert body["corpus_as_of"] == settings.corpus_as_of


def test_search_needs_no_llm(client):
    body = client.get("/search", params={"q": "ค่าชดเชยเลิกจ้าง", "k": 3}).json()
    assert body["in_scope"] is True
    assert len(body["hits"]) == 3
    assert all("มาตรา" in h["citation"] for h in body["hits"])


def test_search_marks_off_topic(client):
    body = client.get("/search", params={"q": "สูตรทำต้มยำกุ้ง"}).json()
    assert body["in_scope"] is False


def test_chat_refuses_a_missing_code_without_an_api_key(client):
    """No Typhoon key is configured in tests; a gap question must still answer,
    because it never reaches the model."""
    body = client.post("/chat", json={"question": "มรดกแบ่งยังไง"}).json()
    assert body["in_scope"] is False
    assert "ประมวลกฎหมายแพ่งและพาณิชย์" in body["answer"]


def test_chat_rejects_an_empty_question(client):
    assert client.post("/chat", json={"question": ""}).status_code == 422


def test_webhook_rejects_an_unsigned_request(client, monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    resp = client.post("/webhook", json=EVENT)
    assert resp.status_code == 403


def test_webhook_rejects_a_forged_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    body = json.dumps(EVENT).encode()
    bad = base64.b64encode(hmac.new(b"wrong", body, hashlib.sha256).digest()).decode()
    resp = client.post("/webhook", content=body,
                       headers={"X-Line-Signature": bad,
                                "Content-Type": "application/json"})
    assert resp.status_code == 403


def test_webhook_is_disabled_until_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "line_channel_secret", "")
    assert client.post("/webhook", json=EVENT).status_code == 503


def test_webhook_accepts_a_signed_request(client, monkeypatch):
    """A valid event must return 200 immediately -- LINE retries anything slower,
    so the answer is produced in a background task, not in the response."""
    monkeypatch.setattr(settings, "line_channel_secret", SECRET)
    handled = []

    async def fake_handle(event):
        handled.append(event)

    monkeypatch.setattr("app.line_bot.handle_event", fake_handle)
    body = json.dumps(EVENT).encode()
    sig = base64.b64encode(
        hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
    resp = client.post("/webhook", content=body,
                       headers={"X-Line-Signature": sig,
                                "Content-Type": "application/json"})
    assert resp.status_code == 200
    assert len(handled) == 1
