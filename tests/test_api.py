"""Testy integracyjne endpointów FastAPI z zamockowanym retrieverem i LLM."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Mockujemy ciężkie zależności ML zanim FastAPI załaduje moduły
for mod in ("fastembed", "fastembed.sparse", "fastembed.sparse.bm25",
            "qdrant_client", "qdrant_client.http", "qdrant_client.http.models",
            "sentence_transformers", "tqdm", "asyncpg", "redis"):
    sys.modules.setdefault(mod, MagicMock())

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from rag.retriever import RetrievedChunk


def _make_chunk(**kwargs) -> RetrievedChunk:
    defaults = dict(
        score=0.85, text="Art. 1. Ustawa reguluje...", act_id="WDU2024001",
        title="Ustawa testowa", year="2024", publisher="WDU", pos="1",
        url="https://isap.sejm.gov.pl/test", chunk_index=0, total_chunks=1,
        is_repealed=False, valid_from_year=2024,
    )
    defaults.update(kwargs)
    return RetrievedChunk(**defaults)


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def mock_internal_secret(monkeypatch):
    monkeypatch.setattr("api.dependencies.INTERNAL_API_SECRET", "test-secret")


@pytest.fixture()
def internal_headers():
    return {"X-Internal-Token": "test-secret", "Content-Type": "application/json"}


# ── /ping ────────────────────────────────────────────────────────────────────

def test_ping_returns_200(client):
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_returns_200_when_qdrant_ok(client):
    mock_retriever = MagicMock()
    mock_retriever.client.get_collection.return_value = MagicMock(
        status="green", vectors_count=1000, points_count=1000
    )
    with patch("api.dependencies.init_retriever", return_value=mock_retriever):
        resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["qdrant_connected"] is True


def test_health_returns_503_when_qdrant_down(client):
    mock_retriever = MagicMock()
    mock_retriever.client.get_collection.side_effect = Exception("connection refused")
    # Patch both init_retriever and the global _retriever state
    with (
        patch("api.dependencies.init_retriever", return_value=mock_retriever),
        patch("api.main.init_retriever", return_value=mock_retriever),
    ):
        resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["qdrant_connected"] is False


# ── /search ───────────────────────────────────────────────────────────────────

def test_search_with_internal_token(client, internal_headers):
    chunks = [_make_chunk()]
    mock_retriever = MagicMock()
    mock_retriever.format_context.return_value = "Kontekst."

    async def fake_thread(fn, *args, **kwargs):
        return chunks

    with (
        patch("api.dependencies.init_retriever", return_value=mock_retriever),
        patch("api.routers.ask.asyncio.to_thread", side_effect=fake_thread),
    ):
        resp = client.post(
            "/search",
            json={"query": "Jakie są prawa pracownika?", "top_k": 3},
            headers=internal_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert data["query"] == "Jakie są prawa pracownika?"


def test_search_empty_query_rejected(client, internal_headers):
    resp = client.post("/search", json={"query": "ab", "top_k": 3}, headers=internal_headers)
    assert resp.status_code == 422


def test_search_top_k_too_large(client, internal_headers):
    resp = client.post(
        "/search",
        json={"query": "Jakie są prawa pracownika?", "top_k": 999},
        headers=internal_headers,
    )
    assert resp.status_code == 422


# ── /ask ─────────────────────────────────────────────────────────────────────

def test_ask_returns_answer(client, internal_headers):
    chunks = [_make_chunk()]
    mock_retriever = MagicMock()
    mock_retriever.format_context.return_value = "Kontekst prawny."

    call_count = 0

    async def fake_thread(fn, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return chunks
        return ("Odpowiedź testowa.", "gpt-4o-mini")

    with (
        patch("api.dependencies.init_retriever", return_value=mock_retriever),
        patch("api.routers.ask.asyncio.to_thread", side_effect=fake_thread),
    ):
        resp = client.post(
            "/ask",
            json={"question": "Jakie są prawa pracownika przy wypowiedzeniu?", "top_k": 3},
            headers=internal_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert "confidence" in data


def test_ask_question_too_short(client, internal_headers):
    resp = client.post("/ask", json={"question": "Co?", "top_k": 3}, headers=internal_headers)
    assert resp.status_code == 422


def test_ask_question_too_long(client, internal_headers):
    resp = client.post(
        "/ask",
        json={"question": "a" * 2001, "top_k": 3},
        headers=internal_headers,
    )
    assert resp.status_code == 422


# ── /api schematy ─────────────────────────────────────────────────────────────

def test_ask_schema_has_temporal_fields(client, internal_headers):
    """Sprawdza że nowe pola temporal RAG są akceptowane przez API."""
    chunks = [_make_chunk()]
    mock_retriever = MagicMock()
    mock_retriever.format_context.return_value = "Kontekst."

    call_count = 0

    async def fake_thread(fn, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return chunks
        return ("Odpowiedź.", "gpt-4o-mini")

    with (
        patch("api.dependencies.init_retriever", return_value=mock_retriever),
        patch("api.routers.ask.asyncio.to_thread", side_effect=fake_thread),
    ):
        resp = client.post(
            "/ask",
            json={
                "question": "Jakie były przepisy o VAT w 2018 roku?",
                "top_k": 3,
                "exclude_repealed": False,
                "as_of_year": 2018,
            },
            headers=internal_headers,
        )

    assert resp.status_code == 200


# ── rate_limit ────────────────────────────────────────────────────────────────

def test_rate_limit_in_process_fallback():
    """Sprawdza że in-process fallback zlicza i blokuje po przekroczeniu limitu."""
    import time
    from fastapi import HTTPException
    from api.rate_limit import _check_fallback, _fallback_buckets

    ip = f"test-ip-{time.time()}"
    _fallback_buckets[ip] = []

    with patch("api.rate_limit.RATE_LIMIT_REQUESTS", 3):
        _check_fallback(ip)
        _check_fallback(ip)
        _check_fallback(ip)
        with pytest.raises(HTTPException) as exc:
            _check_fallback(ip)
        assert exc.value.status_code == 429


def test_is_internal_request_valid(monkeypatch):
    from api.dependencies import is_internal_request as _is_internal_request
    from fastapi import Request

    import api.dependencies as _deps
    monkeypatch.setattr(_deps, "INTERNAL_API_SECRET", "moj-sekret")
    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"X-Internal-Token": "moj-sekret"}
    assert _is_internal_request(mock_req) is True


def test_is_internal_request_wrong_token(monkeypatch):
    from api.dependencies import is_internal_request as _is_internal_request
    from fastapi import Request

    import api.dependencies as _deps
    monkeypatch.setattr(_deps, "INTERNAL_API_SECRET", "moj-sekret")
    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"X-Internal-Token": "zly-token"}
    assert _is_internal_request(mock_req) is False


def test_is_internal_request_empty_secret(monkeypatch):
    from api.dependencies import is_internal_request as _is_internal_request
    from fastapi import Request

    monkeypatch.setattr("api.dependencies.INTERNAL_API_SECRET", "")
    mock_req = MagicMock(spec=Request)
    mock_req.headers = {"X-Internal-Token": "cokolwiek"}
    assert _is_internal_request(mock_req) is False
