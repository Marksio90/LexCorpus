"""
main.py — LexCorpus FastAPI application.

Endpoints:
    GET  /              — API info
    GET  /health        — health check (Qdrant + model status)
    POST /ask           — ask a legal question, get answer + source citations

The /ask endpoint:
  1. Retrieves top-k relevant legal chunks from Qdrant (RAG).
  2. Formats a prompt with retrieved context.
  3. Generates an answer using the local fine-tuned model if available,
     falling back to Anthropic Claude API if not.

Environment variables:
    QDRANT_URL          — Qdrant server URL (default: http://localhost:6333)
    QDRANT_API_KEY      — Qdrant API key (optional)
    QDRANT_COLLECTION   — Collection name (default: lexcorpus)
    LOCAL_MODEL_PATH    — Path to fine-tuned model (optional; enables local inference)
    ANTHROPIC_API_KEY   — Claude API key (fallback when local model not available)
    EMBEDDING_MODEL     — SentenceTransformer model name

Usage:
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.schemas import AskRequest, AskResponse, ErrorResponse, HealthResponse, SourceDocument

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Configuration from environment ──────────────────────────────────────────
QDRANT_PATH = os.getenv("QDRANT_PATH", "data/qdrant")  # local file path, or http://... for server
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "lexcorpus")
LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sdadas/mmlw-retrieval-roberta-large")

# ── Global state (loaded once at startup) ────────────────────────────────────
_retriever = None
_local_model = None
_local_tokenizer = None
_anthropic_client = None


def _init_retriever():
    """Initialize the RAG retriever (lazy, called on first /ask)."""
    global _retriever
    if _retriever is not None:
        return _retriever

    from rag.retriever import LegalRetriever

    _retriever = LegalRetriever(
        model_name=EMBEDDING_MODEL,
        collection=QDRANT_COLLECTION,
        qdrant=QDRANT_PATH,
        api_key=QDRANT_API_KEY,
    )
    log.info("Retriever initialized (Qdrant: %s, collection: %s)", QDRANT_PATH, QDRANT_COLLECTION)
    return _retriever


def _init_local_model():
    """Load the local fine-tuned model if LOCAL_MODEL_PATH is set."""
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
        log.info("Local model loaded successfully")
    except Exception as exc:
        log.warning("Failed to load local model: %s", exc)
        _local_model = None
        _local_tokenizer = None

    return _local_model, _local_tokenizer


def _init_anthropic():
    """Initialize the Anthropic client if API key is available."""
    global _anthropic_client
    if not ANTHROPIC_API_KEY:
        return None
    if _anthropic_client is not None:
        return _anthropic_client

    import anthropic

    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    log.info("Anthropic client initialized")
    return _anthropic_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize resources at startup."""
    log.info("LexCorpus API starting …")
    # Pre-initialize the retriever (loads embedding model + connects to Qdrant)
    try:
        _init_retriever()
    except Exception as exc:
        log.warning("Retriever initialization failed (will retry on first request): %s", exc)

    # Pre-initialize local model if configured
    _init_local_model()

    # Initialize Anthropic client
    _init_anthropic()

    log.info("LexCorpus API ready")
    yield
    log.info("LexCorpus API shutting down")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="LexCorpus API",
    description=(
        "Polish Legal AI — answers legal questions using RAG over ISAP legal acts. "
        "Fine-tuned on Bielik-7B-Instruct with QLoRA."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail=str(exc), error_type="internal_error").model_dump(),
    )


# ── Prompt building ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Jesteś ekspertem ds. polskiego prawa. Odpowiadasz na pytania prawne "
    "na podstawie podanych przepisów prawa polskiego. "
    "Udzielasz dokładnych, zwięzłych odpowiedzi w języku polskim. "
    "Jeśli nie znasz odpowiedzi na podstawie podanych przepisów, mówisz o tym wprost. "
    "Zawsze powołujesz się na konkretne artykuły i akty prawne."
)


def build_prompt(question: str, context: str) -> str:
    """Build a RAG prompt with retrieved context."""
    if context:
        return (
            f"Na podstawie poniższych przepisów prawnych, odpowiedz na pytanie.\n\n"
            f"PRZEPISY:\n{context}\n\n"
            f"PYTANIE: {question}\n\n"
            f"ODPOWIEDŹ:"
        )
    return f"PYTANIE: {question}\n\nODPOWIEDŹ:"


def generate_with_local_model(prompt: str, max_new_tokens: int = 512) -> str:
    """Generate answer using the local fine-tuned model."""
    import torch

    model, tokenizer = _local_model, _local_tokenizer
    full_prompt = f"### Instrukcja:\n{SYSTEM_PROMPT}\n\n### Pytanie:\n{prompt}\n\n### Odpowiedź:\n"

    inputs = tokenizer(full_prompt, return_tensors="pt", truncation=True, max_length=3000)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.3,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )

    input_len = inputs["input_ids"].shape[1]
    generated_ids = output_ids[0][input_len:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def generate_with_claude(prompt: str) -> str:
    """Generate answer using Anthropic Claude API as fallback."""
    client = _init_anthropic()
    if client is None:
        return (
            "Przepraszam, nie mogę wygenerować odpowiedzi — brak skonfigurowanego modelu językowego. "
            "Ustaw zmienną środowiskową LOCAL_MODEL_PATH lub ANTHROPIC_API_KEY."
        )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def generate_answer(prompt: str) -> tuple[str, str]:
    """
    Generate an answer, preferring local model over Claude API.
    Returns (answer_text, model_name_used).
    """
    if _local_model is not None:
        try:
            answer = generate_with_local_model(prompt)
            return answer, LOCAL_MODEL_PATH or "local-model"
        except Exception as exc:
            log.warning("Local model inference failed, falling back to Claude: %s", exc)

    answer = generate_with_claude(prompt)
    return answer, "claude-fallback"


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/", response_model=dict)
async def root() -> dict:
    """API information endpoint."""
    return {
        "name": "LexCorpus API",
        "version": "0.1.0",
        "description": "Polish Legal AI — RAG + fine-tuned model over ISAP legal acts",
        "docs": "/docs",
        "health": "/health",
        "ask": "POST /ask",
    }


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint — checks Qdrant connectivity and model status."""
    qdrant_ok = False
    collection_count = None

    try:
        retriever = _init_retriever()
        info = retriever.client.get_collection(QDRANT_COLLECTION)
        qdrant_ok = True
        collection_count = getattr(info, "points_count", None) or getattr(info, "vectors_count", None)
    except Exception as exc:
        log.warning("Qdrant health check failed: %s", exc)

    model_loaded = _local_model is not None
    embedding_loaded = _retriever is not None and _retriever._model is not None

    return HealthResponse(
        status="ok",
        qdrant_connected=qdrant_ok,
        model_loaded=model_loaded,
        embedding_model_loaded=embedding_loaded,
        collection_count=collection_count,
    )


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """
    Answer a Polish legal question.

    Retrieves relevant passages from the ISAP legal corpus (Qdrant),
    then generates an answer using the local fine-tuned model or Claude API.
    Returns the answer along with source citations.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    log.info("Received question: %s", question[:120])

    # Step 1: Retrieve relevant chunks via RAG
    retrieved_chunks = []
    context_str = ""
    retrieval_used = False

    if request.use_rag:
        try:
            retriever = _init_retriever()
            chunks = retriever.retrieve(
                query=question,
                top_k=request.top_k,
                year_filter=request.year_filter,
                publisher_filter=request.publisher_filter,
            )
            context_str = retriever.format_context(chunks, max_chars=3500)
            retrieved_chunks = chunks
            retrieval_used = True
            log.info("Retrieved %d chunks (top score: %.4f)", len(chunks), chunks[0].score if chunks else 0.0)
        except Exception as exc:
            log.warning("RAG retrieval failed, proceeding without context: %s", exc)

    # Step 2: Build prompt and generate answer
    prompt = build_prompt(question, context_str)
    answer, model_used = generate_answer(prompt)
    log.info("Answer generated by: %s", model_used)

    # Step 3: Build source documents for response
    sources = [
        SourceDocument(
            score=chunk.score,
            act_id=chunk.act_id,
            title=chunk.title,
            year=chunk.year,
            publisher=chunk.publisher,
            pos=chunk.pos,
            url=chunk.url,
            chunk_index=chunk.chunk_index,
            total_chunks=chunk.total_chunks,
            text=chunk.text[:500] + ("…" if len(chunk.text) > 500 else ""),
            citation=chunk.citation(),
        )
        for chunk in retrieved_chunks
    ]

    return AskResponse(
        question=question,
        answer=answer,
        sources=sources,
        model_used=model_used,
        retrieval_used=retrieval_used,
    )


def start() -> None:
    """Entry point for the lexcorpus-api console script."""
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    start()
