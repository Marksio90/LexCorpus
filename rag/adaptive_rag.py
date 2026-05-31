"""
adaptive_rag.py — Query complexity classifier for Adaptive RAG.

Routes queries into complexity classes that drive retrieval strategy:
  TRIVIAL → no retrieval (LLM answers from memory for simple definitions)
  SIMPLE  → standard single-pass hybrid RAG
  COMPLEX → multi-hop: more candidates, more query expansions, iterative retrieval

Extracted from rag/retriever.py to be independently unit-testable.
"""
from __future__ import annotations

import enum
import re


class QueryComplexity(str, enum.Enum):
    """Complexity class that drives retrieval strategy selection."""
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    COMPLEX = "complex"


class ComplexityRouter:
    """
    Classify a Polish legal query into TRIVIAL / SIMPLE / COMPLEX.

    Uses lightweight regex heuristics — no model inference, sub-millisecond.
    Classification drives:
      - TRIVIAL: skip retrieval entirely
      - COMPLEX: increase candidate pool (prefetch_mult × 2) and expansion count (n × 2)
    """

    _TRIVIAL_RE = re.compile(
        r"^("
        r"co to jest|co oznacza|definicja|definicję|czym jest|kim jest|co to"
        r")|"
        r"\b(co to jest|co oznacza|definicja|czym jest)\b",
        re.IGNORECASE,
    )
    _COMPLEX_RE = re.compile(
        r"\b("
        r"jak .{3,25} wpływa|wpływ .{3,20} na"
        r"|porównaj|porównanie|różnica między|różnice między"
        r"|zależność między|w związku z|w kontekście"
        r"|zarówno .{3,20} jak|na tle|jaka jest relacja"
        r"|jak .{3,20} odnosi się"
        r"|łącznie|kumulatywnie|jednocześnie"
        r")\b",
        re.IGNORECASE,
    )
    _MULTI_ACT_RE = re.compile(
        r"(?:ustaw[aą]|kodeks\w*|rozporządzen\w+).{3,50}(?:ustaw[aą]|kodeks\w*|rozporządzen\w+)",
        re.IGNORECASE,
    )

    def classify(self, query: str) -> QueryComplexity:
        words = query.split()
        if len(words) <= 4 and self._TRIVIAL_RE.search(query):
            return QueryComplexity.TRIVIAL
        if self._COMPLEX_RE.search(query) or self._MULTI_ACT_RE.search(query):
            return QueryComplexity.COMPLEX
        return QueryComplexity.SIMPLE
