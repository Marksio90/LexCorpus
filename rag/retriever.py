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
import hashlib
import json
import logging
import re
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
PREFETCH_MULTIPLIER = 6  # fetch 6x candidates for better recall before rerank
EXPAND_N = 3             # 3 alternative queries + original = 4 total
CONTEXT_EXPAND = True    # fetch neighbor chunks for wider context in format_context()


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
    parent_text: str = ""       # populated when parent-child chunking is used
    chunk_type: str = ""        # "child" | "parent" | "" (legacy)

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
        hyde_expander: Callable[[str], str] | None = None,
    ) -> None:
        self.model_name = model_name
        self.rerank_model_name = rerank_model_name
        self.collection = collection
        self.qdrant = qdrant
        self.api_key = api_key
        self.rerank = rerank
        self.query_expander = query_expander  # fn(query, n) -> list[str] of alternatives
        self.hyde_expander = hyde_expander
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

    def _embed_dense_cached(self, query: str) -> list[float]:
        """Cache dense embeddings by query hash to avoid recomputing identical queries."""
        key = hashlib.md5(query.encode()).hexdigest()
        if not hasattr(self, "_embed_cache"):
            self._embed_cache: dict[str, list[float]] = {}
        if key not in self._embed_cache:
            if len(self._embed_cache) > 512:  # max 512 cached queries
                # Remove oldest (first) entry
                self._embed_cache.pop(next(iter(self._embed_cache)))
            self._embed_cache[key] = self._embed_dense(query)
        return self._embed_cache[key]

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
        dense_vector = self._embed_dense_cached(query)
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
                parent_text=payload.get("parent_text", ""),
                chunk_type=payload.get("chunk_type", ""),
            ))
        return results

    def _fetch_neighbor_text(self, chunk: RetrievedChunk, direction: int) -> str:
        """Fetch the adjacent chunk (direction=-1 for prev, +1 for next) from Qdrant."""
        target_index = chunk.chunk_index + direction
        if target_index < 0:
            return ""
        try:
            points, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(key="act_id", match=qmodels.MatchValue(value=chunk.act_id)),
                    qmodels.FieldCondition(key="chunk_index", match=qmodels.MatchValue(value=target_index)),
                ]),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if points:
                return points[0].payload.get("text", "")
        except Exception as exc:
            log.debug("Neighbor fetch failed for %s[%d]: %s", chunk.act_id, target_index, exc)
        return ""

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        year_filter: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        publisher_filter: str | None = None,
        source_type_filter: str | None = None,
        rerank: bool | None = None,
        expand: bool | None = None,
        expand_context: bool = CONTEXT_EXPAND,
    ) -> list[RetrievedChunk]:
        """
        Full pipeline: query expansion → hybrid search → dedup → cross-encoder re-rank.

        Args:
            query: The user's question in Polish.
            top_k: Number of results to return after re-ranking.
            year_filter: Only return acts from this exact year.
            year_from: Only return acts from this year onwards (inclusive).
            year_to: Only return acts up to this year (inclusive).
            publisher_filter: Only return acts from this publisher (e.g. 'WDU').
            rerank: Override instance-level rerank setting for this call.
            expand: Override query expansion for this call (requires query_expander set).
            expand_context: Fetch neighboring chunks and merge into retrieved text.
        """
        use_rerank = self.rerank if rerank is None else rerank
        use_expand = (expand is not False) and (self.query_expander is not None)

        # HyDE: embed a hypothetical document instead of the raw query for first search pass
        hyde_query = query
        if self.hyde_expander is not None:
            try:
                hyde_query = self.hyde_expander(query)
                log.debug("HyDE hypothesis generated (%d chars)", len(hyde_query))
            except Exception as exc:
                log.warning("HyDE generation failed, using original query: %s", exc)

        filter_conditions: list[qmodels.FieldCondition] = []
        if year_filter:
            filter_conditions.append(
                qmodels.FieldCondition(key="year", match=qmodels.MatchValue(value=str(year_filter)))
            )
        if year_from or year_to:
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="year",
                    range=qmodels.Range(
                        gte=str(year_from) if year_from else None,
                        lte=str(year_to) if year_to else None,
                    ),
                )
            )
        if publisher_filter:
            filter_conditions.append(
                qmodels.FieldCondition(key="publisher", match=qmodels.MatchValue(value=publisher_filter))
            )
        if source_type_filter and source_type_filter in SOURCE_TYPE_TO_PUBLISHER:
            publishers = SOURCE_TYPE_TO_PUBLISHER[source_type_filter]
            filter_conditions.append(
                qmodels.FieldCondition(
                    key="source_type",
                    match=qmodels.MatchAny(any=publishers),
                )
            )

        # Auto-route if no explicit filter provided
        if source_type_filter is None:
            routed = _route_query(query)
            if routed == "tax":
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="source_type",
                        match=qmodels.MatchAny(any=["tax_interpretation"]),
                    )
                )
                log.debug("Auto-routed to tax interpretations")
            elif routed == "judgment":
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="source_type",
                        match=qmodels.MatchAny(any=["judgment_nsa", "judgment_sn",
                                                    "judgment_tk", "judgment_common", "judgment_kio"]),
                    )
                )
                log.debug("Auto-routed to judgments")
            elif routed == "legislation":
                filter_conditions.append(
                    qmodels.FieldCondition(
                        key="source_type",
                        match=qmodels.MatchAny(any=["legislation"]),
                    )
                )
                log.debug("Auto-routed to legislation")

        query_filter = qmodels.Filter(must=filter_conditions) if filter_conditions else None

        candidate_limit = top_k * PREFETCH_MULTIPLIER

        # Build list of query variants: HyDE query (or original) + expansions
        queries = [hyde_query]
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

        # Detect if corpus uses parent-child chunking (any child chunk in candidates)
        has_children = any(c.chunk_type == "child" for c in candidates)

        if not use_rerank or len(candidates) <= top_k:
            results = sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]
            if has_children:
                results = self._lift_to_parent(results)
            return self._expand_context(results) if (expand_context and not has_children) else results

        # Cross-encoder re-ranking using the original query (not expansions)
        # Re-rank on child text (precise) before lifting to parent
        pairs = [(query, c.text) for c in candidates]
        ce_scores = self.rerank_model.predict(pairs)
        ranked = sorted(zip(ce_scores, candidates), key=lambda x: x[0], reverse=True)

        results = []
        for ce_score, chunk in ranked[:top_k]:
            chunk.score = round(float(ce_score), 4)
            results.append(chunk)

        if has_children:
            results = self._lift_to_parent(results)
        return self._expand_context(results) if (expand_context and not has_children) else results

    def _expand_context(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Enrich each chunk with neighbor text — one Qdrant query per unique document."""
        result_keys = {f"{c.act_id}___{c.chunk_index}" for c in chunks}

        # Collect unique act_ids and needed neighbor indices
        needed: dict[str, set[int]] = {}
        for chunk in chunks:
            needed.setdefault(chunk.act_id, set())
            needed[chunk.act_id].add(chunk.chunk_index - 1)
            needed[chunk.act_id].add(chunk.chunk_index + 1)

        # Batch fetch: one scroll per document (not per chunk)
        doc_texts: dict[str, dict[int, str]] = {}
        for act_id, indices in needed.items():
            valid = [i for i in indices if i >= 0]
            if not valid:
                continue
            try:
                points, _ = self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=qmodels.Filter(must=[
                        qmodels.FieldCondition(key="act_id", match=qmodels.MatchValue(value=act_id)),
                    ]),
                    limit=max(valid) + 2,
                    with_payload=["chunk_index", "text"],
                    with_vectors=False,
                )
                doc_texts[act_id] = {
                    int(p.payload.get("chunk_index", -1)): p.payload.get("text", "")
                    for p in points
                }
            except Exception as exc:
                log.debug("Batch neighbor fetch failed for %s: %s", act_id, exc)

        for chunk in chunks:
            dt = doc_texts.get(chunk.act_id, {})
            parts = []
            prev_text = dt.get(chunk.chunk_index - 1, "")
            if prev_text and f"{chunk.act_id}___{chunk.chunk_index - 1}" not in result_keys:
                parts.append(prev_text)
            parts.append(chunk.text)
            next_text = dt.get(chunk.chunk_index + 1, "")
            if next_text and f"{chunk.act_id}___{chunk.chunk_index + 1}" not in result_keys:
                parts.append(next_text)
            if len(parts) > 1:
                chunk.text = "\n\n".join(parts)
        return chunks

    def _lift_to_parent(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """
        For child chunks (parent-child mode), replace the child text with the
        parent text so the LLM receives the full 512-token context window.

        The parent_text is embedded in the child's payload at preprocessing time,
        so no extra Qdrant query is needed here.
        """
        seen_parents: set[str] = set()
        result: list[RetrievedChunk] = []

        for chunk in chunks:
            if chunk.chunk_type == "child" and chunk.parent_text:
                # Deduplicate: if two children share the same parent, keep highest-score
                parent_key = f"{chunk.act_id}___{chunk.parent_text[:64]}"
                if parent_key in seen_parents:
                    continue
                seen_parents.add(parent_key)
                chunk.text = chunk.parent_text  # replace child text with parent context
            result.append(chunk)

        return result

    def format_context(self, chunks: list[RetrievedChunk], max_chars: int = 4000) -> str:
        parts = []
        total_chars = 0
        for i, chunk in enumerate(chunks, 1):
            # Use parent_text if available (richer context for LLM)
            display_text = chunk.parent_text if chunk.parent_text else chunk.text
            block = f"[{i}] {chunk.citation()}\n{display_text}"
            if total_chars + len(block) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 200:
                    parts.append(block[:remaining] + "…")
                break
            parts.append(block)
            total_chars += len(block) + 2
        return "\n\n".join(parts)


SOURCE_TYPE_TO_PUBLISHER = {
    "legislation":        ["WDU", "WMP"],
    "judgment_nsa":       ["ADMINISTRATIVE"],
    "judgment_sn":        ["SUPREME"],
    "judgment_tk":        ["CONSTITUTIONAL_TRIBUNAL"],
    "judgment_common":    ["COMMON"],
    "judgment_kio":       ["NATIONAL_APPEAL_CHAMBER"],
    "tax_interpretation": ["KIS"],
}


_LEGISLATION_KEYWORDS = re.compile(
    r"\b(ustawa|rozporządzenie|przepis|artykuł|paragraf|kodeks|dyrektywa|"
    r"obowiązek|uprawnienie|definicja|wymóg|warunek|termin|kara|sankcja|"
    r"ile dni|ile lat|jaki jest|co oznacza|co to jest)\b",
    re.IGNORECASE,
)
_JUDGMENT_KEYWORDS = re.compile(
    r"\b(wyrok|orzeczenie|sąd|sprawa|pozew|apelacja|kasacja|skarga|"
    r"precedens|orzecznictwo|linia orzecznicza|NSA|SN|TK|WSA|KIO|"
    r"jak orzekają|praktyka|czy sąd|czy można zaskarżyć)\b",
    re.IGNORECASE,
)
_TAX_KEYWORDS = re.compile(
    r"\b(interpretacja|KIS|podatek|VAT|PIT|CIT|akcyza|podatk\w+|"
    r"urząd skarbowy|MF|ministerstwo finansów|organ podatkowy|"
    r"deklaracja podatkowa|rozliczenie podatkowe|ulga podatkowa|"
    r"zwolnienie z VAT|stawka VAT|faktura|korekta faktury)\b",
    re.IGNORECASE,
)


def _route_query(query: str) -> str | None:
    """
    Returns suggested source_type_filter based on query keywords.
    Returns None if ambiguous (search everything).
    Only routes when signal is very clear to avoid false positives.
    """
    leg_score = len(_LEGISLATION_KEYWORDS.findall(query))
    jud_score = len(_JUDGMENT_KEYWORDS.findall(query))
    tax_score = len(_TAX_KEYWORDS.findall(query))

    if tax_score >= 2 and jud_score == 0:
        return "tax"        # clearly asking for tax interpretation
    if jud_score >= 2 and leg_score == 0:
        return "judgment"   # clearly about case law
    if leg_score >= 2 and jud_score == 0:
        return "legislation"  # clearly about statutory text
    return None  # ambiguous — search everything


def _make_hyde_expander(api_key: str) -> Callable[[str], str]:
    """Return function that generates a hypothetical legal document passage for HyDE retrieval."""
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package required")

    client = openai.OpenAI(api_key=api_key)
    _hyde_cache: dict[str, str] = {}

    def generate_hypothesis(query: str) -> str:
        key = hashlib.md5(query.encode()).hexdigest()
        if key in _hyde_cache:
            return _hyde_cache[key]
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Jesteś redaktorem aktów prawnych. Napisz fragment (3-5 zdań) "
                            "polskiego przepisu prawnego lub orzeczenia sądowego, który bezpośrednio "
                            "odpowiada na poniższe pytanie. Używaj języka prawniczego, pisz tak jakby "
                            "to był rzeczywisty artykuł ustawy lub teza wyroku. "
                            "Odpowiedz TYLKO tym fragmentem, bez żadnego wstępu."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                temperature=0.1,
                max_tokens=200,
            )
            result = resp.choices[0].message.content.strip()
        except Exception:
            result = query  # fallback: use original query
        _hyde_cache[key] = result
        return result

    return generate_hypothesis


def _make_openai_expander(api_key: str) -> Callable[[str, int], list[str]]:
    """Return a query expansion function backed by OpenAI gpt-4o-mini."""
    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package required for query expansion: pip install openai")

    client = openai.OpenAI(api_key=api_key)
    _expansion_cache: dict[str, list[str]] = {}

    def expand(query: str, n: int) -> list[str]:
        cache_key = hashlib.md5(f"{query}:{n}".encode()).hexdigest()
        if cache_key in _expansion_cache:
            return _expansion_cache[cache_key]
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
        result = [l.strip() for l in lines if l.strip()][:n]
        _expansion_cache[cache_key] = result
        return result

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
