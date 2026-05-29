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
    year_filter: Optional[str] = Field(default=None, description="Filter by exact year, e.g. '2024'")
    year_from: Optional[int] = Field(default=None, description="Filter acts from this year onwards")
    year_to: Optional[int] = Field(default=None, description="Filter acts up to this year (inclusive)")
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
    year_from: Optional[int] = Field(default=None)
    year_to: Optional[int] = Field(default=None)
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


class AnswerConfidence(BaseModel):
    """Pewność odpowiedzi na podstawie jakości retrieval."""
    score: float          # 0.0 – 1.0
    level: str            # "wysoka" | "średnia" | "niska"
    n_sources: int        # liczba źródeł które wspierają odpowiedź
    top_source_score: float
    explanation: str      # 1 zdanie po polsku


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceDocument] = Field(default_factory=list)
    model_used: str
    retrieval_used: bool
    confidence: Optional[AnswerConfidence] = None


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


class SourceBreakdown(BaseModel):
    legislation: int = 0
    judgment_nsa: int = 0
    judgment_sn: int = 0
    judgment_tk: int = 0
    judgment_common: int = 0
    judgment_kio: int = 0
    total: int = 0


class StatsResponse(BaseModel):
    by_source: SourceBreakdown
    total_chunks: int
    collection_name: str
    embedding_model: str
    rerank_enabled: bool
    expand_enabled: bool
    last_ingest: Optional[str] = None   # ISO datetime of last ingest sentinel mtime


class ErrorResponse(BaseModel):
    detail: str
    error_type: str = "error"
