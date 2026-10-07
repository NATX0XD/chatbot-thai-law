# -*- coding: utf-8 -*-
"""The Dockerfile may only COPY data files the .dockerignore lets through.

.dockerignore excludes data/processed/ and data/index/ wholesale and names the
serving files back one by one. A COPY added to the Dockerfile without its
matching "!" line leaves the file out of the build context, and the build stops
with

    "/data/processed/corpus_ksp.jsonl": not found

That is exactly what happened to corpus_ksp.jsonl: it was added to the Dockerfile
long after .dockerignore was written for corpus.jsonl alone, and the failure only
showed up on Render, after the push. The two lists are one thing kept in two
files, so compare them here instead.
"""
from __future__ import annotations

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COPY_SOURCE = re.compile(r"^COPY\s+(\S+)\s+\S+\s*$", re.MULTILINE)


def _read(name: str) -> str:
    with open(os.path.join(BASE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def copied_data_files() -> set[str]:
    return {src for src in COPY_SOURCE.findall(_read("Dockerfile"))
            if src.startswith("data/")}


def allowed_back_in() -> set[str]:
    return {line[1:].strip() for line in _read(".dockerignore").splitlines()
            if line.startswith("!")}


def test_every_data_file_the_image_copies_is_in_the_build_context():
    missing = copied_data_files() - allowed_back_in()
    assert not missing, (
        "the Dockerfile copies these but .dockerignore excludes them, so the "
        f"build will stop at 'not found': {sorted(missing)}")


def test_no_data_file_is_kept_in_the_context_that_nothing_copies():
    """A stale "!" line ships weight nobody reads; 66 MB of corpus is not free."""
    unused = allowed_back_in() - copied_data_files()
    assert not unused, (
        "these survive .dockerignore but no COPY uses them, so they only make "
        f"the build context bigger: {sorted(unused)}")


def test_the_app_imports_nothing_the_server_image_does_not_install():
    """requirements-server.txt leaves pythainlp, torch, sentence-transformers
    and rank_bm25 out to fit the host's memory. A function-level
    `from pythainlp...` in app/flex.py passed every test on a development
    machine, where the package is installed, and took every LINE reply down
    on the server (2026-10-07)."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parent.parent
    absent = re.compile(r"^\s*(?:from|import)\s+(pythainlp|rank_bm25)\b", re.M)
    found = [f"{path.relative_to(root)}: {m.group(1)}"
             for path in sorted((root / "app").rglob("*.py"))
             for m in absent.finditer(path.read_text(encoding="utf-8"))]
    assert not found, found
