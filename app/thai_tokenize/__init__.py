# -*- coding: utf-8 -*-
# Vendored from PyThaiNLP 5.0.5 (Apache-2.0), https://github.com/PyThaiNLP/pythainlp
# Files taken unchanged except for import paths: newmm.py, tcc_p.py, trie.py,
# _utils.py, words_th.txt.
"""The newmm word tokenizer, carved out of PyThaiNLP.

BM25 tokenises with newmm, so the server needs newmm and nothing else. Importing
it from the package is not an option on a 512 MB host: `import pythainlp` costs
266 MB resident (measured), because pythainlp/tokenize/__init__.py eagerly builds
three separate word tries and pythainlp/__init__.py pulls in the spell checker,
the POS tagger and the transliterator with their corpora.

Only the word trie is built here, lazily, and it costs 51 MB.

Tokenisation must stay bit-identical to what built the index -- a query token that
no longer matches the postings retrieves nothing -- so these are the upstream
files, with the import lines rewritten and no other edit. The equivalence is
checked against the installed pythainlp in tests/test_tokenizer_parity.py.
"""
from __future__ import annotations

import os
from typing import List

from app.thai_tokenize._utils import (apply_postprocessors,
                                      rejoin_formatted_num, strip_whitespace)
from app.thai_tokenize.trie import Trie

WORDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "words_th.txt")

_TRIE: Trie | None = None


def thai_words() -> frozenset:
    """Read words_th.txt the way pythainlp.corpus.get_corpus does.

    utf-8-sig, no per-line strip, empty lines dropped, comments kept -- entries
    such as "ก ข ไม่กระดิกหู" contain spaces, so stripping would be wrong.
    """
    with open(WORDS_PATH, encoding="utf-8-sig") as f:
        return frozenset(filter(None, f.read().splitlines()))


def default_trie() -> Trie:
    global _TRIE
    if _TRIE is None:
        _TRIE = Trie(thai_words())
    return _TRIE


def word_tokenize(text: str, keep_whitespace: bool = True,
                  join_broken_num: bool = True) -> List[str]:
    """pythainlp.tokenize.word_tokenize restricted to engine="newmm".

    The postprocessor order matches upstream: rejoin numerics first, because
    stripping whitespace first would let "1, 234" close up into one token.
    """
    if not text or not isinstance(text, str):
        return []

    from app.thai_tokenize.newmm import segment

    segments = segment(text, default_trie())

    postprocessors = []
    if join_broken_num:
        postprocessors.append(rejoin_formatted_num)
    if not keep_whitespace:
        postprocessors.append(strip_whitespace)

    return apply_postprocessors(segments, postprocessors)
