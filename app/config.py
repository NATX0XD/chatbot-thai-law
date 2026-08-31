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
    llm_temperature: float = 0.2

    # --- LINE ---
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    # this bot's own userId, used to spot an @-mention in a group. Fetched once
    # from GET /v2/bot/info; leaving it blank only weakens group mention detection
    # on older webhook payloads that lack the isSelf flag.
    line_bot_user_id: str = ""

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
    top_k_final: int = 6
    rrf_k: int = 60
    # Fusion weights. Dense carries roughly four times the signal of BM25 on Thai
    # questions: a short query like "เจ้าหนี้ทวงหนี้ตี 1 ผิดไหม" tokenises into
    # common words that score high on BM25 against unrelated acts, which pushed
    # the section that answers it out of the results entirely. Measured on the
    # probe set in ingest/tune_fusion.py, 2:1 lifts correct-act-in-top-3 from
    # 9/12 to 11/12. BM25 still earns its place on exact vocabulary and section
    # numbers, so it is down-weighted rather than removed.
    weight_dense: float = 2.0
    weight_bm25: float = 0.5
    # Seats reserved for the dense retriever's own best results, so a chunk it
    # ranks first cannot be pushed out by RRF. BM25 gets none: its top hit on a
    # short Thai query is frequently irrelevant.
    guarantee_top: int = 2
    # The in-scope gate reads the raw cosine, not the fused RRF score -- RRF depends
    # on rank alone, so an off-topic question and a perfect match get the same value.
    # Calibrated by ingest/calibrate.py: on-topic probes bottom out at 0.592 and
    # off-topic ones top out at 0.496, so 0.54 sits in the gap.
    # BM25 is deliberately NOT part of this gate: off-topic questions reach 15.1
    # while a valid one can sit at 12.6, so the sparse score carries no signal about
    # whether the corpus knows the answer. It still drives ranking.
    min_dense_sim: float = 0.54   # BGE-M3 cosine

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
    corpus_as_of: str = "พ.ศ. 2563"
    max_answer_chars: int = 1800

    @property
    def corpus_path(self) -> str:
        return os.path.join(PROCESSED_DIR, "corpus.jsonl")

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
