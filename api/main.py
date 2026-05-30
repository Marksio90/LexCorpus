"""
main.py — LexCorpus FastAPI application.

Endpoints are split across routers:
    api/routers/ask.py     — POST /ask, POST /ask/stream
    api/routers/search.py  — POST /search
    api/routers/sync.py    — GET /sync/status, POST /sync/trigger, GET /stats
    api/routers/private.py — POST /ask/private, DELETE /private-collection/{user_id}
                             POST /internal/enqueue-document

Usage:
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.schemas import ErrorResponse, HealthResponse
from api.result_cache import get_cache
from api.dependencies import (
    init_retriever, init_local_model, init_openai,
    QDRANT_COLLECTION, EMBEDDING_MODEL,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("LexCorpus API starting …")
    try:
        init_retriever()
    except Exception as exc:
        log.warning("Retriever warmup failed (will retry on first request): %s", exc)
    init_local_model()
    init_openai()
    from api.sync import start_scheduler
    start_scheduler()
    log.info("LexCorpus API ready")
    yield
    log.info("LexCorpus API shutting down")


app = FastAPI(
    title="LexCorpus API",
    description="Polish Legal AI — RAG over ISAP legislation, SAOS judgments, EUR-Lex and KIS.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Internal-Token"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail=str(exc), error_type="internal_error").model_dump(),
    )


# ── Include routers ────────────────────────────────────────────────────────────
from api.routers.ask import router as ask_router
from api.routers.search import router as search_router
from api.routers.sync import router as sync_router
from api.routers.private import router as private_router
from api.routers.agent import router as agent_router

app.include_router(ask_router)
app.include_router(search_router)
app.include_router(sync_router)
app.include_router(private_router)
app.include_router(agent_router)


# ── Utility endpoints ──────────────────────────────────────────────────────────

@app.get("/", response_model=dict)
async def root() -> dict:
    return {
        "name": "LexCorpus API",
        "version": "0.2.0",
        "description": "Polish Legal AI — RAG + fine-tuned model over Polish legal acts",
        "docs": "/docs",
        "health": "/health",
        "ask": "POST /ask",
    }

@app.get("/ping")
async def ping() -> dict:
    """Lightweight liveness probe — no external calls. Use this for uptime monitors."""
    return {"ok": True}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Full readiness check — verifies Qdrant connectivity and model state.
    Returns HTTP 503 if critical dependencies are unavailable.
    """
    qdrant_ok = False
    collection_count = None
    try:
        retriever = init_retriever()
        info = retriever.client.get_collection(QDRANT_COLLECTION)
        qdrant_ok = True
        collection_count = getattr(info, "points_count", None) or getattr(info, "vectors_count", None)
    except Exception as exc:
        log.warning("Qdrant health check failed: %s", exc)

    from api.dependencies import _retriever, _local_model
    embedding_loaded = _retriever is not None and getattr(_retriever, "_dense_model", None) is not None

    status = "ok" if qdrant_ok else "degraded"
    response = HealthResponse(
        status=status,
        qdrant_connected=qdrant_ok,
        model_loaded=_local_model is not None,
        embedding_model_loaded=embedding_loaded,
        collection_count=collection_count,
    )

    if not qdrant_ok:
        return JSONResponse(status_code=503, content=response.model_dump())
    return response


def start() -> None:
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")


if __name__ == "__main__":
    start()
