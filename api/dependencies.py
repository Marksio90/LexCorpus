"""
dependencies.py — Shared state, init functions, and helpers for all routers.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import time
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from api.schemas import AskResponse, AnswerConfidence, SourceDocument, publisher_to_source_type
from api.result_cache import get_cache
from api.rate_limit import check_rate_limit

if TYPE_CHECKING:
    from rag.retriever import RetrievedChunk

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
QDRANT_PATH = os.getenv("QDRANT_PATH", "data/qdrant")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "lexcorpus")
LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sdadas/mmlw-retrieval-roberta-large")
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() not in ("false", "0", "no")
EXPAND_ENABLED = os.getenv("EXPAND_ENABLED", "true").lower() not in ("false", "0", "no")
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")
_DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Global model state ────────────────────────────────────────────────────────
_retriever = None
_local_model = None
_local_tokenizer = None
_openai_client = None
_pg_pool = None


def init_retriever():
    global _retriever
    if _retriever is not None:
        return _retriever

    from rag.retriever import LegalRetriever, _make_openai_expander, _make_hyde_expander

    expander = None
    if EXPAND_ENABLED and OPENAI_API_KEY:
        expander = _make_openai_expander(OPENAI_API_KEY)

    hyde_expander = None
    if os.getenv("HYDE_ENABLED", "true").lower() not in ("false", "0", "no") and OPENAI_API_KEY:
        hyde_expander = _make_hyde_expander(OPENAI_API_KEY)

    _retriever = LegalRetriever(
        model_name=EMBEDDING_MODEL,
        rerank_model_name=RERANK_MODEL,
        collection=QDRANT_COLLECTION,
        qdrant=QDRANT_PATH,
        api_key=QDRANT_API_KEY,
        rerank=RERANK_ENABLED,
        query_expander=expander,
        hyde_expander=hyde_expander,
    )
    log.info("Retriever initialized (Qdrant: %s, collection: %s)", QDRANT_PATH, QDRANT_COLLECTION)
    return _retriever


def init_local_model():
    global _local_model, _local_tokenizer
    if not LOCAL_MODEL_PATH:
        return None, None
    if _local_model is not None:
        return _local_model, _local_tokenizer

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    log.info("Loading local model from %s …", LOCAL_MODEL_PATH)
    try:
        _local_tokenizer = AutoTokenizer.from_pretrained(LOCAL_MODEL_PATH)
        _local_model = AutoModelForCausalLM.from_pretrained(
            LOCAL_MODEL_PATH,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        _local_model.eval()
        log.info("Local model loaded")
    except Exception as exc:
        log.warning("Failed to load local model: %s", exc)
        _local_model = None
        _local_tokenizer = None
    return _local_model, _local_tokenizer


def init_openai():
    global _openai_client
    if not OPENAI_API_KEY:
        return None
    if _openai_client is not None:
        return _openai_client

    from openai import OpenAI
    _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    log.info("OpenAI client initialized (model: %s)", OPENAI_MODEL)
    return _openai_client


async def get_pg_pool():
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    if not _DATABASE_URL:
        return None
    try:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(_DATABASE_URL, min_size=2, max_size=10, command_timeout=5)
        log.info("Connected to PostgreSQL")
    except Exception as exc:
        log.warning("PostgreSQL unavailable: %s", exc)
        _pg_pool = None
    return _pg_pool


# ── Auth helpers ──────────────────────────────────────────────────────────────

def is_internal_request(request: Request) -> bool:
    token = request.headers.get("X-Internal-Token", "")
    return bool(INTERNAL_API_SECRET and token == INTERNAL_API_SECRET)


def require_internal(request: Request) -> None:
    secret = os.getenv("NEWSLETTER_INTERNAL_SECRET", "")
    token = request.headers.get("x-internal-secret", "")
    if not secret or token != secret:
        raise HTTPException(status_code=403, detail="Forbidden")


async def verify_api_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    plain = auth[len("Bearer "):]
    token_hash = hashlib.sha256(plain.encode()).hexdigest()
    pool = await get_pg_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Baza danych niedostępna.")
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT id, "userId" FROM "ApiToken" WHERE "tokenHash"=$1 AND "revokedAt" IS NULL',
                token_hash,
            )
            if row:
                await conn.execute(
                    'UPDATE "ApiToken" SET "lastUsedAt"=NOW(), "requestCount"="requestCount"+1 WHERE id=$1',
                    row["id"],
                )
    except Exception as exc:
        log.warning("Token verification error: %s", exc)
        row = None
    if row is None and plain:
        raise HTTPException(status_code=401, detail="Nieprawidłowy lub unieważniony token API.")
    return row["userId"] if row else None


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Business logic ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Jesteś ekspertem ds. polskiego prawa. Odpowiadasz na pytania prawne "
    "na podstawie podanych przepisów prawa polskiego. "
    "Udzielasz dokładnych, zwięzłych odpowiedzi w języku polskim. "
    "Jeśli nie znasz odpowiedzi na podstawie podanych przepisów, mówisz o tym wprost. "
    "Zawsze powołujesz się na konkretne artykuły i akty prawne używając znaczników [1], [2] itd. "
    "odpowiadających numeracji podanych przepisów."
)

SOURCE_TYPE_TO_PUBLISHER = {
    "legislation": "WDU",
    "judgment_nsa": "ADMINISTRATIVE",
    "judgment_sn": "SUPREME",
    "judgment_tk": "CONSTITUTIONAL_TRIBUNAL",
    "judgment_common": "COMMON",
    "judgment_kio": "NATIONAL_APPEAL_CHAMBER",
    "tax_interpretation": "KIS",
}


def build_prompt(question: str, context: str) -> str:
    if context:
        return (
            "Na podstawie poniższych przepisów prawnych odpowiedz na pytanie. "
            "Cytuj źródła używając numerów w nawiasach kwadratowych, np. [1], [2], "
            "zgodnie z numeracją w sekcji PRZEPISY poniżej.\n\n"
            f"PRZEPISY:\n{context}\n\n"
            f"PYTANIE: {question}\n\n"
            "ODPOWIEDŹ (powołuj się na [numer] przy każdym twierdzeniu):"
        )
    return f"PYTANIE: {question}\n\nODPOWIEDŹ:"


def compute_confidence(chunks: list) -> AnswerConfidence:
    if not chunks:
        return AnswerConfidence(
            score=0.0, level="niska", n_sources=0, top_source_score=0.0,
            explanation="Brak dokumentów — nie udało się znaleźć powiązanych przepisów.",
        )
    scores = [c.score for c in chunks]
    top_score = max(scores)
    supporting = sum(1 for s in scores[:3] if s >= 0.60)
    coverage = supporting / min(3, len(scores))
    combined = round(top_score * 0.6 + coverage * 0.4, 3)
    if combined >= 0.80:
        level = "wysoka"
        explanation = f"Odpowiedź oparta na {len(chunks)} źródłach o wysokiej trafności (najwyższy score: {top_score:.0%})."
    elif combined >= 0.60:
        level = "średnia"
        explanation = f"Znaleziono powiązane przepisy, ale pokrycie jest częściowe (score: {top_score:.0%})."
    else:
        level = "niska"
        explanation = f"Dokumenty powiązane z pytaniem mają niski score ({top_score:.0%})."
    return AnswerConfidence(score=combined, level=level, n_sources=len(chunks),
                            top_source_score=round(top_score, 3), explanation=explanation)


def chunk_to_source(chunk) -> SourceDocument:
    return SourceDocument(
        score=chunk.score, act_id=chunk.act_id, title=chunk.title,
        year=chunk.year, publisher=chunk.publisher,
        source_type=publisher_to_source_type(chunk.publisher),
        pos=chunk.pos, url=chunk.url, chunk_index=chunk.chunk_index,
        total_chunks=chunk.total_chunks,
        text=chunk.text[:500] + ("…" if len(chunk.text) > 500 else ""),
        citation=chunk.citation(),
    )


def resolve_publisher_filter(source_type_filter: str | None, publisher_filter: str | None) -> str | None:
    if publisher_filter:
        return publisher_filter
    if source_type_filter:
        return SOURCE_TYPE_TO_PUBLISHER.get(source_type_filter)
    return None


def generate_with_local_model(prompt: str, max_new_tokens: int = 512) -> str:
    import torch
    model, tokenizer = _local_model, _local_tokenizer
    full_prompt = f"### Instrukcja:\n{SYSTEM_PROMPT}\n\n### Pytanie:\n{prompt}\n\n### Odpowiedź:\n"
    inputs = tokenizer(full_prompt, return_tensors="pt", truncation=True, max_length=3000)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        output_ids = model.generate(
            **inputs, max_new_tokens=max_new_tokens,
            do_sample=True, temperature=0.3, top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated_ids = output_ids[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def generate_with_openai(prompt: str) -> str:
    client = init_openai()
    if client is None:
        return "Przepraszam, brak skonfigurowanego modelu językowego. Ustaw OPENAI_API_KEY."
    response = client.chat.completions.create(
        model=OPENAI_MODEL, max_tokens=1024,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def generate_answer(prompt: str) -> tuple[str, str]:
    if _local_model is not None:
        try:
            return generate_with_local_model(prompt), LOCAL_MODEL_PATH or "local-model"
        except Exception as exc:
            log.warning("Local model failed, falling back to OpenAI: %s", exc)
    return generate_with_openai(prompt), OPENAI_MODEL
