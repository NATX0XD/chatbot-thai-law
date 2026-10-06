# -*- coding: utf-8 -*-
"""Which dataset each test module runs against.

The bot serves the networking textbook now (DATASET=network). The Teachers
Council path is kept whole, and so are its tests: every module that was written
for it runs with DATASET=ksp, exactly as it did before the switch. Only the
modules named in NETWORK_TESTS run against the textbook.
"""
import pytest

from app.config import settings

NETWORK_TESTS = {"test_book", "test_extract_book"}


@pytest.fixture(autouse=True)
def dataset(request, monkeypatch):
    name = request.module.__name__.rsplit(".", 1)[-1]
    monkeypatch.setattr(settings, "dataset",
                        "network" if name in NETWORK_TESTS else "ksp")
