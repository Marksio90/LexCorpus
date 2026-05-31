"""
dependencies.py — Shared state, init functions, and helpers for all routers.
"""
from __future__ import annotations

import hashlib
import logging
import os

from fastapi import HTTPException, Request

from api.schemas import AnswerConfidence, SourceDocument, publisher_to_source_type
from api.rate_limit import check_rate_limit  # noqa: F401

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
QDRANT_PATH = os.getenv("QDRANT_PATH", "data/qdrant")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "lexcorpus")
LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# vLLM — OpenAI-compatible local inference (e.g. Bielik-11B via docker-compose.vllm.yml)
# When VLLM_ENABLED=true, generate_with_openai() routes to the vLLM endpoint instead
# of the real OpenAI API. Query expansion and HyDE still use OPENAI_API_KEY if set.
VLLM_ENABLED = os.getenv("VLLM_ENABLED", "false").lower() not in ("false", "0", "no")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "speakleash/Bielik-11B-v2.3-Instruct")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sdadas/mmlw-retrieval-roberta-large-v2")
RERANK_MODEL = os.getenv("RERANK_MODEL", "sdadas/polish-reranker-large-ranknet")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() not in ("false", "0", "no")
EXPAND_ENABLED = os.getenv("EXPAND_ENABLED", "true").lower() not in ("false", "0", "no")
HYDE_ENABLED = os.getenv("HYDE_ENABLED", "true").lower() not in ("false", "0", "no")
CRAG_ENABLED = os.getenv("CRAG_ENABLED", "true").lower() not in ("false", "0", "no")
ADAPTIVE_RAG_ENABLED = os.getenv("ADAPTIVE_RAG_ENABLED", "true").lower() not in ("false", "0", "no")
EMBED_QUERY_PREFIX = os.getenv("EMBED_QUERY_PREFIX", "[query]: ")
INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")
_DATABASE_URL = os.getenv("DATABASE_URL", "")

# Bielik-11B uses a specific chat template; detect by model path
_LOCAL_MODEL_IS_BIELIK = LOCAL_MODEL_PATH and "bielik" in (LOCAL_MODEL_PATH or "").lower()

# ── Global model state ────────────────────────────────────────────────────────
_retriever = None
_llm_provider = None       # active LLMProvider instance (set by init_llm_provider)
_local_model = None        # kept for health-check compatibility (_local_model is not None)
_local_tokenizer = None
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
    if HYDE_ENABLED and OPENAI_API_KEY:
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
        query_prefix=EMBED_QUERY_PREFIX,
        crag_enabled=CRAG_ENABLED,
        adaptive_rag=ADAPTIVE_RAG_ENABLED,
    )
    log.info(
        "Retriever initialized (model=%s, reranker=%s, CRAG=%s, Adaptive=%s, prefix=%r)",
        EMBEDDING_MODEL, RERANK_MODEL, CRAG_ENABLED, ADAPTIVE_RAG_ENABLED, EMBED_QUERY_PREFIX,
    )
    return _retriever


def init_llm_provider():
    """
    Build and cache the active LLMProvider based on configuration.

    Priority (highest to lowest):
      1. LocalTransformersProvider  — if LOCAL_MODEL_PATH is set
      2. VLLMProvider               — if VLLM_ENABLED=true
      3. OpenAIProvider             — if OPENAI_API_KEY is set

    If multiple backends are configured, they are chained in a FallbackProvider
    so the next in priority is tried automatically if the primary fails.
    """
    global _llm_provider, _local_model, _local_tokenizer
    if _llm_provider is not None:
        return _llm_provider

    from api.llm_providers import (
        FallbackProvider, LocalTransformersProvider, OpenAIProvider, VLLMProvider,
    )

    providers = []

    if LOCAL_MODEL_PATH:
        try:
            local = LocalTransformersProvider(
                LOCAL_MODEL_PATH,
                is_bielik="bielik" in LOCAL_MODEL_PATH.lower(),
            )
            # Keep references for backward-compat health check in main.py
            _local_model = local._model
            _local_tokenizer = local._tokenizer
            providers.append(local)
        except Exception as exc:
            log.warning("Failed to load local model '%s': %s", LOCAL_MODEL_PATH, exc)

    if VLLM_ENABLED:
        providers.append(VLLMProvider(VLLM_BASE_URL, VLLM_MODEL))
        log.info("vLLM provider configured (base_url=%s, model=%s)", VLLM_BASE_URL, VLLM_MODEL)

    if OPENAI_API_KEY:
        providers.append(OpenAIProvider(OPENAI_API_KEY, OPENAI_MODEL))
        log.info("OpenAI provider configured (model=%s)", OPENAI_MODEL)

    if not providers:
        log.warning("No LLM provider configured — set OPENAI_API_KEY or LOCAL_MODEL_PATH")
        return None

    _llm_provider = providers[0] if len(providers) == 1 else FallbackProvider(providers)
    log.info("LLM provider ready: %s", _llm_provider.model_id)
    return _llm_provider


def get_llm_provider():
    """Return the cached LLMProvider, initializing it if necessary."""
    if _llm_provider is None:
        return init_llm_provider()
    return _llm_provider


def init_local_model():
    """Backward-compatible wrapper — delegates to init_llm_provider()."""
    init_llm_provider()
    return _local_model, _local_tokenizer


def init_openai():
    """Backward-compatible wrapper — delegates to init_llm_provider()."""
    init_llm_provider()
    return None  # OpenAI client is now internal to OpenAIProvider


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
    "Jesteś ekspertem ds. polskiego prawa specjalizującym się w legislacji i orzecznictwie. "
    "Odpowiadasz wyłącznie na podstawie podanych przepisów i wyroków sądowych. "
    "Udzielasz dokładnych, zwięzłych odpowiedzi w języku polskim. "
    "Jeśli podane przepisy nie dają wystarczającej podstawy do udzielenia odpowiedzi, "
    "mówisz o tym wprost — nie spekulujesz ani nie wymyślasz przepisów. "
    "Zawsze cytuj konkretne artykuły i akty prawne używając znaczników [1], [2] itd. "
    "odpowiadających numeracji w sekcji PRZEPISY. "
    "Nie cytuj przepisów oznaczonych jako 'niepewne' bez wyraźnego zaznaczenia tej niepewności."
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


def _sigmoid(x: float) -> float:
    """Normalize cross-encoder logit to (0, 1) range."""
    import math
    return 1.0 / (1.0 + math.exp(-x))


def compute_confidence(chunks: list) -> AnswerConfidence:
    if not chunks:
        return AnswerConfidence(
            score=0.0, level="niska", n_sources=0, top_source_score=0.0,
            explanation="Brak dokumentów — nie udało się znaleźć powiązanych przepisów.",
        )
    # Cross-encoder scores are raw logits (range ~-10..+10); normalize to 0-1 via sigmoid
    # so that thresholds below are meaningful regardless of model scale.
    norm_scores = [_sigmoid(c.score) for c in chunks]
    top_score = max(norm_scores)
    supporting = sum(1 for s in norm_scores[:3] if s >= 0.60)
    coverage = supporting / min(3, len(norm_scores))
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


def generate_answer(prompt: str) -> tuple[str, str]:
    """
    Generate an answer using the active LLMProvider.

    Returns (answer_text, model_identifier). Backed by FallbackProvider so
    the next configured backend is tried automatically if the primary fails.
    """
    provider = get_llm_provider()
    if provider is None:
        return (
            "Przepraszam, brak skonfigurowanego modelu językowego. "
            "Ustaw OPENAI_API_KEY lub LOCAL_MODEL_PATH.",
            "none",
        )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return provider.generate(messages)
