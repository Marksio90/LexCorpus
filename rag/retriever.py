"""
retriever.py — Hybrid retrieval + query expansion + cross-encoder re-ranking.

Pipeline:
  1. Query expansion: LLM generates N alternative phrasings of the question
  2. Hybrid search: for each query variant → dense + BM25 sparse → RRF fusion → candidates
  3. Deduplication: merge candidate pools by (act_id, chunk_index)
  4. Cross-encoder re-ranking: scores each (original_query, candidate) pair → final top_k

Query expansion is driven by an injected callable so the retriever has no hard OpenAI dependency.

Usage as module:
    from rag.retriever import LegalRetriever
    retriever = LegalRetriever(query_expander=my_expand_fn)
    results = retriever.retrieve("Jakie są obowiązki pracodawcy?", top_k=5)

Usage as script:
    python rag/retriever.py --query "Jakie są prawa pracownika?"
    python rag/retriever.py --query "Jakie są prawa pracownika?" --no-rerank --no-expand
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from fastembed.sparse.bm25 import Bm25
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import CrossEncoder, SentenceTransformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DEFAULT_MODEL = "sdadas/mmlw-retrieval-roberta-large"
DEFAULT_RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
DEFAULT_COLLECTION = "lexcorpus"
DEFAULT_QDRANT_PATH = "data/qdrant"
DEFAULT_TOP_K = 5
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
PREFETCH_MULTIPLIER = 4  # fetch 4x candidates per query before RRF + re-rank
EXPAND_N = 2             # number of alternative queries to generate (+ original = 3 total)


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
        rerank_model_name: str = DEFAULT_RERANK_MODEL,
        collection: str = DEFAULT_COLLECTION,
        qdrant: str = DEFAULT_QDRANT_PATH,
        api_key: str | None = None,
        rerank: bool = True,
        query_expander: Callable[[str, int], list[str]] | None = None,
    ) -> None:
        self.model_name = model_name
        self.rerank_model_name = rerank_model_name
        self.collection = collection
        self.qdrant = qdrant
        self.api_key = api_key
        self.rerank = rerank
        self.query_expander = query_expander  # fn(query, n) -> list[str] of alternatives
        self._dense_model: SentenceTransformer | None = None
        self._sparse_model: Bm25 | None = None
        self._rerank_model: CrossEncoder | None = None
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
    def rerank_model(self) -> CrossEncoder:
        if self._rerank_model is None:
            log.info("Loading cross-encoder '%s' …", self.rerank_model_name)
            self._rerank_model = CrossEncoder(self.rerank_model_name)
        return self._rerank_model

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

    def _search_one(
        self,
        query: str,
        candidate_limit: int,
        query_filter: qmodels.Filter | None,
    ) -> list[RetrievedChunk]:
        """Run a single hybrid RRF search and return candidates."""
        dense_vector = self._embed_dense(query)
        sparse_vector = self._embed_sparse(query)
        prefetch_limit = candidate_limit

        hits = self.client.query_points(
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
            limit=candidate_limit,
            with_payload=True,
        ).points

        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(RetrievedChunk(
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
        return results

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        year_filter: str | None = None,
        publisher_filter: str | None = None,
        rerank: bool | None = None,
        expand: bool | None = None,
    ) -> list[RetrievedChunk]:
        """
        Full pipeline: query expansion → hybrid search → dedup → cross-encoder re-rank.

        Args:
            query: The user's question in Polish.
            top_k: Number of results to return after re-ranking.
            year_filter: Only return acts from this year.
            publisher_filter: Only return acts from this publisher (e.g. 'WDU').
            rerank: Override instance-level rerank setting for this call.
            expand: Override query expansion for this call (requires query_expander set).
        """
        use_rerank = self.rerank if rerank is None else rerank
        use_expand = (expand is not False) and (self.query_expander is not None)

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

        candidate_limit = top_k * PREFETCH_MULTIPLIER

        # Build list of query variants: original + expansions
        queries = [query]
        if use_expand:
            try:
                alternatives = self.query_expander(query, EXPAND_N)
                queries.extend(alternatives)
                log.info("Query expansion: %d variants total", len(queries))
            except Exception as exc:
                log.warning("Query expansion failed, using original only: %s", exc)

        # Search with each variant and merge, preserving best score per chunk
        seen: OrderedDict[str, RetrievedChunk] = OrderedDict()
        for q in queries:
            for chunk in self._search_one(q, candidate_limit, query_filter):
                key = f"{chunk.act_id}___{chunk.chunk_index}"
                if key not in seen or chunk.score > seen[key].score:
                    seen[key] = chunk

        candidates = list(seen.values())

        if not use_rerank or len(candidates) <= top_k:
            return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]

        # Cross-encoder re-ranking using the original query (not expansions)
        pairs = [(query, c.text) for c in candidates]
        ce_scores = self.rerank_model.predict(pairs)
        ranked = sorted(zip(ce_scores, candidates), key=lambda x: x[0], reverse=True)

        results = []
        for ce_score, chunk in ranked[:top_k]:
            chunk.score = round(float(ce_score), 4)
            results.append(chunk)
        return results

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


def _make_openai_expander(api_key: str) -> Callable[[str, int], list[str]]:
    """Return a query expansion function backed by OpenAI gpt-4o-mini."""
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package required for query expansion: pip install openai")

    client = openai.OpenAI(api_key=api_key)

    def expand(query: str, n: int) -> list[str]:
        system = (
            "Jesteś asystentem prawnym. Wygeneruj dokładnie {n} alternatywne sformułowania "
            "podanego pytania prawnego w języku polskim, używając różnych słów kluczowych "
            "i terminologii prawnej. Zwróć TYLKO listę alternatyw, po jednym na linię, "
            "bez numeracji i bez oryginalnego pytania."
        ).format(n=n)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        lines = response.choices[0].message.content.strip().splitlines()
        return [l.strip() for l in lines if l.strip()][:n]

    return expand


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid retrieval for Polish legal docs.")
    parser.add_argument("--query", required=True, help="Question in Polish")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant", default=DEFAULT_QDRANT_PATH)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    parser.add_argument("--no-rerank", action="store_true", help="Disable cross-encoder re-ranking")
    parser.add_argument("--no-expand", action="store_true", help="Disable query expansion")
    parser.add_argument("--openai-key", default=None, help="OpenAI API key for query expansion")
    parser.add_argument("--year", default=None)
    parser.add_argument("--publisher", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    expander = None
    if not args.no_expand and args.openai_key:
        expander = _make_openai_expander(args.openai_key)

    retriever = LegalRetriever(
        model_name=args.model,
        rerank_model_name=args.rerank_model,
        collection=args.collection,
        qdrant=args.qdrant,
        api_key=args.api_key,
        rerank=not args.no_rerank,
        query_expander=expander,
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
