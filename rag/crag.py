"""
crag.py — Corrective Retrieval Augmented Generation (CRAG) gate.

Filters retrieved chunks by cross-encoder relevance before passing them to the
LLM. Prevents the model from citing unrelated or incorrect statutes.

Scoring thresholds:
  score <= LOW_THRESHOLD  → "incorrect" — chunk dropped entirely
  score <= MID_THRESHOLD  → "ambiguous" — chunk kept but flagged in citation
  score >  MID_THRESHOLD  → "correct"   — chunk used normally

Extracted from rag/retriever.py to be independently unit-testable and
configurable without modifying LegalRetriever internals.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag.retriever import RetrievedChunk

log = logging.getLogger(__name__)

# Read thresholds from env so operators can tune without code changes.
DEFAULT_LOW_THRESHOLD = float(os.getenv("CRAG_LOW_THRESHOLD", "-3.0"))
DEFAULT_MID_THRESHOLD = float(os.getenv("CRAG_MID_THRESHOLD", "0.0"))


class CRAGGate:
    """
    Cross-encoder relevance gate for retrieved chunks.

    Args:
        rerank_model: A sentence-transformers CrossEncoder instance.
        low_threshold: CE score below which a chunk is dropped ("incorrect").
        mid_threshold: CE score below which a chunk is flagged ("ambiguous").
    """

    def __init__(
        self,
        rerank_model,
        low_threshold: float = DEFAULT_LOW_THRESHOLD,
        mid_threshold: float = DEFAULT_MID_THRESHOLD,
    ) -> None:
        self._model = rerank_model
        self.low_threshold = low_threshold
        self.mid_threshold = mid_threshold

    def filter(
        self,
        query: str,
        candidates: list["RetrievedChunk"],
        already_reranked: bool = False,
    ) -> list["RetrievedChunk"]:
        """
        Score candidates and drop/flag low-confidence chunks.

        Args:
            query: The original user question (used for CE scoring).
            candidates: Retrieved chunks to evaluate.
            already_reranked: If True, reuse chunk.score as CE score (avoids 2nd CE pass).

        Returns:
            Filtered list with crag_status set on each chunk.
        """
        if not candidates:
            return candidates

        if not already_reranked:
            pairs = [(query, c.text) for c in candidates]
            try:
                ce_scores = self._model.predict(pairs)
            except Exception as exc:
                log.warning("CRAG CE scoring failed, skipping gate: %s", exc)
                return candidates
        else:
            ce_scores = [c.score for c in candidates]

        result = []
        filtered = 0
        for chunk, score in zip(candidates, ce_scores):
            s = float(score)
            if s <= self.low_threshold:
                chunk.crag_status = "incorrect"
                filtered += 1
                continue
            chunk.crag_status = "ambiguous" if s <= self.mid_threshold else "correct"
            result.append(chunk)

        if filtered:
            log.info("CRAG gate filtered %d/%d low-confidence chunks", filtered, len(candidates))
        return result
