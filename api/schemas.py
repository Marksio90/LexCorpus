"""
schemas.py — Pydantic models for the LexCorpus FastAPI application.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceType = Literal["legislation", "judgment_nsa", "judgment_sn", "judgment_tk", "judgment_common", "judgment_kio", "unknown"]


def publisher_to_source_type(publisher: str) -> SourceType:
    mapping = {
        "ADMINISTRATIVE": "judgment_nsa",
        "SUPREME": "judgment_sn",
        "CONSTITUTIONAL_TRIBUNAL": "judgment_tk",
        "COMMON": "judgment_common",
        "NATIONAL_APPEAL_CHAMBER": "judgment_kio",
        "WDU": "legislation",
        "WMP": "legislation",
    }
    return mapping.get(publisher, "unknown")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=2000,
        description="Pytanie prawne w języku polskim",
        examples=["Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?"])
    top_k: int = Field(default=5, ge=1, le=20)
    year_filter: Optional[str] = Field(default=None, description="Filter by year, e.g. '2024'")
    publisher_filter: Optional[str] = Field(default=None,
        description="Filter by publisher/court type: WDU, WMP, ADMINISTRATIVE, SUPREME, CONSTITUTIONAL_TRIBUNAL, COMMON")
    source_type_filter: Optional[SourceType] = Field(default=None,
        description="Filter by source type: legislation | judgment_nsa | judgment_sn | judgment_tk | judgment_common")
    use_rag: bool = Field(default=True)


class SearchRequest(BaseModel):
    """Request body for POST /search — pure retrieval without LLM generation."""
    query: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    year_filter: Optional[str] = Field(default=None)
    publisher_filter: Optional[str] = Field(default=None)
    source_type_filter: Optional[SourceType] = Field(default=None)


class SourceDocument(BaseModel):
    score: float
    act_id: str
    title: str
    year: str
    publisher: str
    source_type: SourceType = Field(default="unknown")
    pos: str
    url: str
    chunk_index: int
    total_chunks: int = Field(default=1)
    text: str
    citation: str


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceDocument] = Field(default_factory=list)
    model_used: str
    retrieval_used: bool


class SearchResponse(BaseModel):
    query: str
    results: list[SourceDocument]
    total: int


class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    model_loaded: bool
    embedding_model_loaded: bool
    collection_count: Optional[int] = None


class ErrorResponse(BaseModel):
    detail: str
    error_type: str = "error"
