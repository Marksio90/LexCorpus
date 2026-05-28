"""
retriever.py — Semantic retrieval from Qdrant for LexCorpus RAG.

Given a user query (in Polish), embeds it with the same model used during ingestion
(sdadas/mmlw-retrieval-roberta-large), searches Qdrant for top-k similar chunks,
and returns structured results with score and metadata.

Usage as module:
    from rag.retriever import LegalRetriever
    retriever = LegalRetriever()
    results = retriever.retrieve("Jakie są obowiązki pracodawcy?", top_k=5)

Usage as script:
    python rag/retriever.py --query "Jakie są prawa pracownika?"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DEFAULT_MODEL = "sdadas/mmlw-retrieval-roberta-large"
DEFAULT_COLLECTION = "lexcorpus"
DEFAULT_QDRANT_PATH = "data/qdrant"
DEFAULT_TOP_K = 5


@dataclass
class RetrievedChunk:
    score: float
    text: str
    act_id: str
    title: str
    year: str
    publisher: str
    pos: str
    url: str
    chunk_index: int
    total_chunks: int

    def as_dict(self) -> dict:
        return asdict(self)

    def citation(self) -> str:
        """Format a human-readable citation string for this chunk."""
        parts = []
        if self.title:
            parts.append(self.title)
        if self.year:
            parts.append(f"({self.year})")
        if self.pos:
            parts.append(f"poz. {self.pos}")
        if self.url:
            parts.append(f"<{self.url}>")
        if not parts:
            parts.append(f"act_id={self.act_id}")
        return " ".join(parts)


class LegalRetriever:
    """
    Semantic retriever for Polish legal documents stored in Qdrant.

    The retriever is lazy — the model and client are loaded on first use.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        collection: str = DEFAULT_COLLECTION,
        qdrant: str = DEFAULT_QDRANT_PATH,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.collection = collection
        self.qdrant = qdrant
        self.api_key = api_key
        self._model: SentenceTransformer | None = None
        self._client: QdrantClient | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            log.info("Loading embedding model '%s' …", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            log.info("Connecting to Qdrant (%s) …", self.qdrant)
            if self.qdrant == ":memory:":
                self._client = QdrantClient(":memory:")
            elif self.qdrant.startswith("http"):
                self._client = QdrantClient(url=self.qdrant, api_key=self.api_key, timeout=30)
            else:
                from pathlib import Path as _Path
                _Path(self.qdrant).mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=self.qdrant)
        return self._client

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string into a normalized vector."""
        vector = self.model.encode(
            query,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vector.tolist()

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float | None = None,
        year_filter: str | None = None,
        publisher_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Retrieve top-k relevant chunks for a query.

        Args:
            query: The user's question in Polish.
            top_k: Number of results to return.
            score_threshold: Minimum cosine similarity score (0–1).
            year_filter: Only return acts from this year.
            publisher_filter: Only return acts from this publisher (e.g. 'WDU').

        Returns:
            List of RetrievedChunk objects sorted by descending score.
        """
        query_vector = self.embed_query(query)

        # Build optional filters
        filter_conditions: list[qmodels.FieldCondition] = []
        if year_filter:
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="year",
                    match=qmodels.MatchValue(value=str(year_filter)),
                )
            )
        if publisher_filter:
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="publisher",
                    match=qmodels.MatchValue(value=publisher_filter),
                )
            )

        query_filter = (
            qmodels.Filter(must=filter_conditions) if filter_conditions else None
        )

        search_results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
            with_payload=True,
        ).points

        chunks = []
        for hit in search_results:
            payload = hit.payload or {}
            chunk = RetrievedChunk(
                score=round(float(hit.score), 4),
                text=payload.get("text", ""),
                act_id=payload.get("act_id", ""),
                title=payload.get("title", ""),
                year=str(payload.get("year", "")),
                publisher=payload.get("publisher", "WDU"),
                pos=str(payload.get("pos", "")),
                url=payload.get("url", ""),
                chunk_index=int(payload.get("chunk_index", 0)),
                total_chunks=int(payload.get("total_chunks", 1)),
            )
            chunks.append(chunk)

        return chunks

    def format_context(self, chunks: list[RetrievedChunk], max_chars: int = 4000) -> str:
        """
        Format retrieved chunks into a single context string for the LLM prompt.
        Includes citations above each chunk.
        """
        parts = []
        total_chars = 0

        for i, chunk in enumerate(chunks, 1):
            citation = chunk.citation()
            block = f"[{i}] {citation}\n{chunk.text}"
            if total_chars + len(block) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 200:
                    block = block[:remaining] + "…"
                    parts.append(block)
                break
            parts.append(block)
            total_chars += len(block) + 2  # +2 for separating newlines

        return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve relevant legal chunks for a query.")
    parser.add_argument("--query", required=True, help="Question in Polish")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--url", default=DEFAULT_QDRANT_URL)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--year", default=None, help="Filter by year")
    parser.add_argument("--publisher", default=None, help="Filter by publisher (WDU/WMP)")
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    retriever = LegalRetriever(
        model_name=args.model,
        collection=args.collection,
        qdrant_url=args.url,
        api_key=args.api_key,
    )

    results = retriever.retrieve(
        args.query,
        top_k=args.top_k,
        score_threshold=args.score_threshold,
        year_filter=args.year,
        publisher_filter=args.publisher,
    )

    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        print(f"\nQuery: {args.query}")
        print(f"Found {len(results)} results:\n")
        for i, r in enumerate(results, 1):
            print(f"[{i}] Score: {r.score:.4f} | {r.citation()}")
            print(f"     {r.text[:300]}{'…' if len(r.text) > 300 else ''}")
            print()


if __name__ == "__main__":
    main()
