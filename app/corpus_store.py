# -*- coding: utf-8 -*-
"""Random access to corpus.jsonl without holding it in memory.

Parsing all 27,203 chunks into dicts costs 97 MB resident -- measured -- because
every chunk becomes six Python objects plus the strings. A query only ever looks
at a few dozen of them, so this keeps a byte offset per line (218 KB) and parses
on demand. Behaves like a read-only list: len(), indexing, iteration.

The offsets are built once at startup by scanning the file for newlines, which
takes about 40 ms for a 63 MB file and avoids shipping a separate sidecar that
could fall out of step with the corpus.
"""
from __future__ import annotations

import json
import os
import threading


class CorpusStore:
    def __init__(self, path: str):
        self.path = path
        self.offsets: list[int] = []
        pos = 0
        with open(path, "rb") as f:
            for line in f:
                if line.strip():
                    self.offsets.append(pos)
                pos += len(line)
        self._fh = open(path, "rb")
        # one shared file handle with a lock: seek+read is two calls and the
        # webhook answers events concurrently, so an unguarded handle would let
        # one request read from another's offset
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self.offsets)

    def __getitem__(self, i: int) -> dict:
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self)))]
        if i < 0:
            i += len(self.offsets)
        with self._lock:
            self._fh.seek(self.offsets[i])
            line = self._fh.readline()
        return json.loads(line)

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()


def open_corpus(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return CorpusStore(path)
