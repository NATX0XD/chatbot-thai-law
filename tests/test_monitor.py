# -*- coding: utf-8 -*-
"""The live-traffic buffer and the endpoint that reads it.

/recent returns other people's questions and the answers they were given, so the
test that matters most here is the one asserting it stays shut without the token.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import monitor
from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def clean():
    monitor._events.clear()
    monitor._people.clear()
    before = settings.monitor_token
    yield
    settings.monitor_token = before
    monitor._events.clear()
    monitor._people.clear()


def test_people_are_numbered_in_the_order_they_first_write():
    for uid in ("Ualice", "Ubob", "Ualice", "Ucarol"):
        monitor.record(source="user", user=uid, text="สวัสดี")
    assert [e["who"] for e in monitor.recent()] == [
        "คนที่ 3", "คนที่ 1", "คนที่ 2", "คนที่ 1"]       # newest first


def test_the_raw_line_user_id_is_never_stored():
    monitor.record(source="user", user="U1234567890abcdef", text="สวัสดี")
    assert "U1234567890abcdef" not in repr(monitor.recent())


def test_the_question_and_the_answer_are_both_kept():
    entry = monitor.record(source="user", user="Ualice", text="ถามอะไรสักอย่าง")
    monitor.finish(entry, answer="ตอบตามข้อ 7", in_scope=True)
    got = monitor.recent()[0]
    assert got["question"] == "ถามอะไรสักอย่าง"
    assert got["answer"] == "ตอบตามข้อ 7"
    assert got["answered"] is not None


def test_the_answer_is_truncated_not_dropped():
    entry = monitor.record(source="web", user="", text="q")
    monitor.finish(entry, answer="ก" * (monitor.MAX_ANSWER + 500))
    assert len(monitor.recent()[0]["answer"]) == monitor.MAX_ANSWER


def test_the_buffer_forgets_the_oldest_rather_than_growing():
    for i in range(monitor.CAPACITY + 20):
        monitor.record(source="web", user="", text=f"q{i}")
    assert len(monitor.recent(monitor.CAPACITY)) == monitor.CAPACITY


def test_recent_is_closed_when_no_token_is_configured():
    settings.monitor_token = ""
    assert TestClient(app).get("/recent").status_code == 404


def test_recent_is_closed_to_a_wrong_token():
    settings.monitor_token = "secret"
    client = TestClient(app)
    # 404, not 403: a 403 would confirm to a stranger that there is something here
    assert client.get("/recent").status_code == 404
    assert client.get("/recent?token=guess").status_code == 404


def test_recent_returns_the_traffic_to_the_right_token():
    settings.monitor_token = "secret"
    entry = monitor.record(source="user", user="Ualice", text="ถามเรื่องจรรยาบรรณ")
    monitor.finish(entry, answer="ตามข้อ 7", in_scope=True)
    body = TestClient(app).get("/recent?token=secret").json()
    assert body["summary"]["people"] == 1
    assert body["events"][0]["who"] == "คนที่ 1"
    assert body["events"][0]["answer"] == "ตามข้อ 7"
