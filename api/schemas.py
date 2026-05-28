"""
schemas.py — Pydantic models for the LexCorpus FastAPI application.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request body for POST /ask."""

    question: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Pytanie prawne w języku polskim / Legal question in Polish",
        examples=["Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?"],
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of relevant document chunks to retrieve",
    )
    year_filter: Optional[str] = Field(
        default=None,
        description="Optionally filter retrieved documents by year (e.g. '2023')",
    )
    publisher_filter: Optional[str] = Field(
        default=None,
        description="Optionally filter by publisher: 'WDU' (Dziennik Ustaw) or 'WMP' (Monitor Polski)",
    )
    use_rag: bool = Field(
        default=True,
        description="If True, retrieve context from Qdrant before generating the answer",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "question": "Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?",
                    "top_k": 5,
                    "year_filter": None,
                    "publisher_filter": "WDU",
                    "use_rag": True,
                }
            ]
        }
    }


class SourceDocument(BaseModel):
    """A single retrieved source document chunk."""

    score: float = Field(..., description="Cosine similarity score (0–1)")
    act_id: str = Field(..., description="Unique act identifier")
    title: str = Field(..., description="Title of the legal act")
    year: str = Field(..., description="Year of publication")
    publisher: str = Field(..., description="Publisher code (WDU or WMP)")
    pos: str = Field(..., description="Position number in the journal")
    url: str = Field(..., description="ELI URL of the act")
    chunk_index: int = Field(..., description="Index of this chunk within the act")
    text: str = Field(..., description="The actual text of the retrieved chunk")
    citation: str = Field(..., description="Human-readable citation string")


class AskResponse(BaseModel):
    """Response body for POST /ask."""

    question: str = Field(..., description="The original question")
    answer: str = Field(..., description="The generated legal answer in Polish")
    sources: list[SourceDocument] = Field(
        default_factory=list,
        description="Retrieved source document chunks used to generate the answer",
    )
    model_used: str = Field(
        ...,
        description="The model that generated the answer (local or claude-fallback)",
    )
    retrieval_used: bool = Field(
        ...,
        description="Whether RAG retrieval was used",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "question": "Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?",
                    "answer": "Zgodnie z Kodeksem Pracy, pracownik ma prawo do okresu wypowiedzenia...",
                    "sources": [],
                    "model_used": "claude-fallback",
                    "retrieval_used": True,
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str = Field(..., description="'ok' if service is healthy")
    qdrant_connected: bool = Field(..., description="Whether Qdrant is reachable")
    model_loaded: bool = Field(..., description="Whether the local LLM is loaded")
    embedding_model_loaded: bool = Field(..., description="Whether the embedding model is loaded")
    collection_count: Optional[int] = Field(
        default=None, description="Number of vectors in the Qdrant collection"
    )


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Error message")
    error_type: str = Field(default="error", description="Error type identifier")
