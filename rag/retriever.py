"""
retriever.py — Hybrid retrieval (dense + BM25 sparse, RRF fusion) from Qdrant.

Given a user query (in Polish), embeds it with both a dense model (sentence-transformers)
and a sparse BM25 model (fastembed), then uses Qdrant's native RRF fusion to combine
results from both search paths into a single ranked list.

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
from pathlib import Path

from fastembed.sparse.bm25 import Bm25
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
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
PREFETCH_MULTIPLIER = 3  # fetch 3x candidates from each path before RRF fusion


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
    Hybrid retriever for Polish legal documents stored in Qdrant.

    Combines dense semantic search (sentence-transformers) and sparse BM25 keyword
    search using Qdrant's Reciprocal Rank Fusion (RRF). Models are loaded lazily.
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
        self._dense_model: SentenceTransformer | None = None
        self._sparse_model: Bm25 | None = None
        self._client: QdrantClient | None = None

    @property
    def dense_model(self) -> SentenceTransformer:
        if self._dense_model is None:
            log.info("Loading dense model '%s' …", self.model_name)
            self._dense_model = SentenceTransformer(self.model_name)
        return self._dense_model

    @property
    def sparse_model(self) -> Bm25:
        if self._sparse_model is None:
            log.info("Loading BM25 sparse model …")
            self._sparse_model = Bm25("Qdrant/bm25")
        return self._sparse_model

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            log.info("Connecting to Qdrant (%s) …", self.qdrant)
            if self.qdrant == ":memory:":
                self._client = QdrantClient(":memory:")
            elif self.qdrant.startswith("http"):
                self._client = QdrantClient(url=self.qdrant, api_key=self.api_key, timeout=30)
            else:
                Path(self.qdrant).mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=self.qdrant)
        return self._client

    def _embed_dense(self, query: str) -> list[float]:
        vector = self.dense_model.encode(query, normalize_embeddings=True, convert_to_numpy=True)
        return vector.tolist()

    def _embed_sparse(self, query: str) -> qmodels.SparseVector:
        sparse = next(iter(self.sparse_model.query_embed(query)))
        return qmodels.SparseVector(
            indices=sparse.indices.tolist(),
            values=sparse.values.tolist(),
        )

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        year_filter: str | None = None,
        publisher_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Hybrid retrieval: dense + BM25 sparse with RRF fusion.

        Args:
            query: The user's question in Polish.
            top_k: Number of results to return after fusion.
            year_filter: Only return acts from this year.
            publisher_filter: Only return acts from this publisher (e.g. 'WDU').
        """
        dense_vector = self._embed_dense(query)
        sparse_vector = self._embed_sparse(query)

        filter_conditions: list[qmodels.FieldCondition] = []
        if year_filter:
            filter_conditions.append(
                qmodels.FieldCondition(key="year", match=qmodels.MatchValue(value=str(year_filter)))
            )
        if publisher_filter:
            filter_conditions.append(
                qmodels.FieldCondition(key="publisher", match=qmodels.MatchValue(value=publisher_filter))
            )
        query_filter = qmodels.Filter(must=filter_conditions) if filter_conditions else None

        prefetch_limit = top_k * PREFETCH_MULTIPLIER
        search_results = self.client.query_points(
            collection_name=self.collection,
            prefetch=[
                qmodels.Prefetch(
                    query=dense_vector,
                    using=DENSE_VECTOR_NAME,
                    limit=prefetch_limit,
                    filter=query_filter,
                ),
                qmodels.Prefetch(
                    query=sparse_vector,
                    using=SPARSE_VECTOR_NAME,
                    limit=prefetch_limit,
                    filter=query_filter,
                ),
            ],
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        ).points

        chunks = []
        for hit in search_results:
            payload = hit.payload or {}
            chunks.append(RetrievedChunk(
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
            ))
        return chunks

    def format_context(self, chunks: list[RetrievedChunk], max_chars: int = 4000) -> str:
        parts = []
        total_chars = 0
        for i, chunk in enumerate(chunks, 1):
            block = f"[{i}] {chunk.citation()}\n{chunk.text}"
            if total_chars + len(block) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 200:
                    parts.append(block[:remaining] + "…")
                break
            parts.append(block)
            total_chars += len(block) + 2
        return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid retrieval for Polish legal docs.")
    parser.add_argument("--query", required=True, help="Question in Polish")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant", default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--year", default=None)
    parser.add_argument("--publisher", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    retriever = LegalRetriever(
        model_name=args.model,
        collection=args.collection,
        qdrant=args.qdrant,
        api_key=args.api_key,
    )

    results = retriever.retrieve(
        args.query,
        top_k=args.top_k,
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
