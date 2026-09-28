# -*- coding: utf-8 -*-
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
# raw/       downloaded source files, never written to
# processed/ what the pipeline produces and what gets handed in or shipped
# index/     derived from processed/, safe to delete and rebuild
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
INDEX_DIR = os.path.join(DATA_DIR, "index")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=os.path.join(BASE_DIR, ".env"),
                                      env_file_encoding="utf-8", extra="ignore")

    # --- Typhoon (OpenAI-compatible) ---
    typhoon_api_key: str = ""
    typhoon_base_url: str = "https://api.opentyphoon.ai/v1"
    typhoon_model: str = "typhoon-v2.5-30b-a3b-instruct"
    typhoon_fallback_model: str = "typhoon-v2.1-12b-instruct"
    llm_timeout: float = 60.0

    # --- Gemini (third in the chain, only if a key is set) ---
    # Typhoon is a research service its own docs call rate limited and not for
    # high-throughput use, so a second provider is the difference between "the
    # bot is quiet today" and "the bot answers". Same prompt, same guards; it is
    # a different writer for the same retrieved sections, never a second opinion
    # on the law.
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model: str = "gemini-3.6-flash"
    llm_max_tokens: int = 1200
    # Zero, not a little above it. This is a citation-bound task: the wording is
    # supposed to follow the retrieved text, and sampling is what lets the writer
    # drift off it -- rendering a rule's "พึง" as "ต้อง", pointing at อนุข้อ (ก)
    # for a sentence that sits under (ข), adding a deadline the section does not
    # state. Variety has no value here and the failure it buys is expensive.
    llm_temperature: float = 0.0

    # --- LINE ---
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    # this bot's own userId, used to spot an @-mention in a group. Fetched once
    # from GET /v2/bot/info; leaving it blank only weakens group mention detection
    # on older webhook payloads that lack the isSelf flag.
    line_bot_user_id: str = ""

    # --- live monitoring ---
    # Shared secret for GET /recent, which returns the questions people have just
    # asked. Blank turns the endpoint off entirely rather than leaving it open:
    # the service is on the public internet and those are other people's messages.
    monitor_token: str = ""

    # --- embeddings ---
    # "local"  sentence-transformers on CPU; what the index is built with
    # "api"    the same checkpoint hosted behind an OpenAI-compatible endpoint,
    #          so the server needs no torch and fits a 512 MB instance
    # Whatever serves "api" must be the same checkpoint that built vectors.npy.
    # Cloudflare Workers AI was measured at cosine 0.999999 against the local
    # model, which is what makes reusing the index legitimate; a provider that
    # merely hosts a model of the same name is not enough. Verify a new one with
    # tests/test_embed_parity.py before pointing production at it.
    embed_backend: str = "local"
    embed_model: str = "BAAI/bge-m3"
    embed_api_model: str = "@cf/baai/bge-m3"
    # https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_timeout: float = 20.0

    # --- retrieval ---
    top_k_dense: int = 30
    top_k_bm25: int = 30
    # How many rules the model is shown. Raised from 6 after acceptance testing:
    # "จรรยาบรรณต่อผู้รับบริการมีกี่ข้อ" was answered "1 ข้อ" because only one of
    # the five had been retrieved. Measured with ingest/tune_fusion.py, recall of
    # the rule that answers the question goes 96% -> 98% at 8 and stops there.
    top_k_final: int = 8
    rrf_k: int = 60
    # Fusion weights. On the general-law corpus dense carried far more signal
    # than BM25 -- a short Thai query tokenises into common words that score high
    # against 29,485 unrelated sections -- and 3.0:0.25 was measured over 6,994
    # labelled questions.
    #
    # That reverses on this corpus, and the reason is its size. 334 chunks of
    # Council regulations share very little vocabulary: "เพิกถอนใบอนุญาต" and
    # "แตกความสามัคคี" appear in a handful of rules each, so an exact word match
    # is strong evidence rather than a coincidence. Re-measured with
    # `python -m ingest.tune_fusion` over the fifty labelled questions in
    # data/eval/ksp_questions.jsonl:
    #
    #                      doc@1  doc@3  rule@1  rule@6
    #   1.0:1.0 (here)      78%    96%     68%     96%
    #   3.0:0.25 (was)      82%    88%     66%     92%
    #   dense only          82%    90%     58%     92%
    #
    # rule@6 is the metric that decides whether a correct answer is reachable at
    # all, and it is the one that improves. doc@1 gives up two questions for
    # three on doc@3 and two on rule@6; on fifty probes none of those margins is
    # large, but they all point the same way.
    weight_dense: float = 1.0
    weight_bm25: float = 1.0
    # Seats reserved for each retriever's own best results, so a chunk it ranks
    # first cannot be pushed out by RRF's known failure -- a hit ranked #1 by one
    # retriever and absent from the other's list scores 1/61, below two mid-table
    # hits that score ~1/31 each.
    #
    # BM25 used to get none of these, because its top hit on a short Thai query
    # was frequently irrelevant against a corpus of 733 acts. With the weights
    # above, giving it one seat is worth a point of doc@3 and a point of rule@6.
    # A superseded rule can never take a reserved seat; see app/retriever.py.
    #
    # Raised from 1 to 3 for the teacher-ethics corpus, where the dense encoder
    # has a blind spot BM25 does not. ข้อบังคับฯ 2550 writes each duty out four
    # times, once per profession, so four chunks differ only in their opening
    # noun and embed almost identically; for "อบายมุขหรือเสพสิ่งเสพติดอยู่ในข้อใด"
    # BM25 ranked all four 1-4 and dense ranked none of them inside its top 30,
    # so one reserved seat admitted the rule for ผู้บริหารการศึกษา and left the
    # rule for ครู out of the evidence entirely. Recall on the 50 labelled
    # questions is 98.0% at every value from 1 to 4 -- it costs nothing there.
    guarantee_top: int = 2
    guarantee_bm25: int = 3
    # The in-scope gate reads the raw cosine, not the fused RRF score -- RRF depends
    # on rank alone, so an off-topic question and a perfect match get the same value.
    #
    # Re-measured on the teacher-ethics corpus with `python -m ingest.calibrate`
    # over the sixty-five probes in data/eval/ksp_questions.jsonl:
    #
    #   answerable                     0.524 – 0.822
    #   not a legal question           0.318 – 0.397
    #   legal, but not in this corpus  0.438 – 0.742
    #
    # The first two separate cleanly and 0.46 sits in the gap; the old 0.54 was
    # calibrated against a corpus 88 times larger and refused one answerable
    # question outright.
    #
    # The third group overlaps the first completely, and always will: every one
    # of those questions is about a teacher and retrieves a real Council
    # regulation. No threshold can separate them, which is what app/coverage.py
    # is for.
    #
    # BM25 is deliberately NOT part of this gate: a question about a teacher's
    # pay scores 41.8 while an answerable one can sit at 9.3, so the sparse score
    # carries no signal about whether the corpus knows the answer. It still
    # drives ranking.
    min_dense_sim: float = 0.46   # BGE-M3 cosine

    # --- checking a citation against the text it points at ---
    # Logs rather than blocks. app/support.py explains what has to be fixed
    # before it can decide anything: the claim window reads backwards from the
    # citation, and answers often put the sentence after it, which produced a
    # 5-in-12 flag rate on answers that were correct.
    claim_check_blocks: bool = False

    # --- reranking ---
    # Off until measured. See app/rerank.py for why, and run
    # `python -m ingest.eval_retrieval --rerank` before turning it on.
    rerank_enabled: bool = False
    rerank_model: str = "@cf/baai/bge-reranker-base"
    # how many fused candidates to send. More is more accurate and more tokens;
    # 12 covers twice the six that reach the model.
    rerank_candidates: int = 12
    rerank_timeout: float = 15.0

    # --- answer policy ---
    corpus_as_of: str = "8 เมษายน พ.ศ. 2569"
    max_answer_chars: int = 1800

    # Which corpus the index is built from and served against. The general-law
    # corpus is still in the repo and still works -- point this at it and rebuild
    # to get the old bot back:
    #
    #   CORPUS_FILE=corpus.jsonl python -m ingest.build_index
    #
    # but the thresholds and the coverage rules in app/coverage.py are tuned for
    # the file named here, so the two are a pair.
    corpus_file: str = "corpus_ksp.jsonl"

    @property
    def corpus_path(self) -> str:
        return os.path.join(PROCESSED_DIR, self.corpus_file)

    @property
    def vectors_path(self) -> str:
        return os.path.join(INDEX_DIR, "vectors.npy")

    @property
    def bm25_path(self) -> str:
        """The fitted rank_bm25 model. Build-time only -- 202 MB resident."""
        return os.path.join(INDEX_DIR, "bm25.pkl")

    @property
    def bm25_compact_path(self) -> str:
        """Serving form of the same model: flat numpy postings, ~8 MB."""
        return os.path.join(INDEX_DIR, "bm25_compact.npz")

    @property
    def bm25_vocab_path(self) -> str:
        return os.path.join(INDEX_DIR, "bm25_vocab.json")


settings = Settings()
