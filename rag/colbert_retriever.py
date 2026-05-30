"""
colbert_retriever.py — ColBERT late-interaction retrieval for Polish legal text.

ColBERT (Contextualized Late Interaction over BERT, Khattab & Zaharia 2020) stores
per-token embeddings rather than a single pooled vector and scores documents with:

    Score(q, d) = Σ_{i ∈ query_tokens} max_{j ∈ doc_tokens} sim(q_i, d_j)

This "MaxSim" operator lets each query token find its best matching document
token independently, which handles Polish morphology (inflections, compound forms)
far better than single-vector retrieval.

Architecture
────────────
  ColBERTRetriever   — encodes queries/docs and scores with MaxSim; used as a
                       plug-in reranker inside LegalRetriever.

  ColBERTIndexBuilder — builds a token-level on-disk index over chunks.jsonl
                        (numpy .npy shards in data/colbert/), and provides an
                        approximate MaxSim search for standalone use.

Integration with LegalRetriever
────────────────────────────────
  The ColBERT reranker is injected into LegalRetriever via the new optional
  `colbert_reranker` parameter. If set, it runs AFTER the cross-encoder step
  (or as a replacement when cross-encoder is disabled) and reranks the final
  top_k pool using MaxSim scores.

  Example::

      from rag.colbert_retriever import ColBERTRetriever
      from rag.retriever import LegalRetriever

      colbert = ColBERTRetriever()
      retriever = LegalRetriever(colbert_reranker=colbert)
      results = retriever.retrieve("Jakie są obowiązki pracodawcy?", top_k=5)

  In retriever.py patch (see integration note at bottom of this file):
  — add ``colbert_reranker: ColBERTRetriever | None = None`` to __init__
  — call ``colbert_reranker.rerank(query, results, top_k)`` after cross-encoder step

Usage as script
───────────────
  # Build index:
  python rag/colbert_retriever.py \\
      --build data/processed/chunks.jsonl \\
      --index-dir data/colbert

  # Search existing index:
  python rag/colbert_retriever.py \\
      --query "obowiązki pracodawcy wypowiedzenie" \\
      --index-dir data/colbert \\
      --top-k 5

  # Rerank Qdrant results with ColBERT:
  python rag/colbert_retriever.py \\
      --rerank-demo "Jakie są prawa pracownika?" \\
      --qdrant data/qdrant

Requirements
────────────
  transformers, torch, numpy   (all already in pyproject.toml)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

if TYPE_CHECKING:
    # Avoid circular import — only for type hints
    from rag.retriever import RetrievedChunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────────────────────────

# mmlw-retrieval-roberta-large-v2 supports token-level embeddings (hidden states)
# and already has Polish vocabulary — best default for this corpus.
DEFAULT_MODEL = "sdadas/mmlw-retrieval-roberta-large-v2"
# True multilingual ColBERT checkpoint (lower coverage but proper ColBERT training)
COLBERT_MULTILINGUAL_MODEL = "colbert-ir/colbertv2.0"

DEFAULT_INDEX_DIR = Path("data/colbert")
DEFAULT_BATCH_SIZE = 32
MAX_QUERY_TOKENS = 64
MAX_DOC_TOKENS = 256
SHARD_SIZE = 50_000   # number of doc token matrices per .npy shard


# ── token-level encoding helpers ──────────────────────────────────────────────


def _mean_pool(
    token_embeddings: torch.Tensor,
    attention_mask: torch.Tensor,
) -> torch.Tensor:
    """Mean pool over non-padding token positions."""
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return (token_embeddings * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    """L2-normalise each row of a 2-D array in-place."""
    norms = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.where(norms > 0, norms, 1.0)


# ── core ColBERT implementation ───────────────────────────────────────────────


class ColBERTRetriever:
    """
    ColBERT late-interaction reranker for Polish legal text.

    Provides token-level encoding and MaxSim scoring. Designed to plug into
    LegalRetriever as a post-Qdrant reranker — it does NOT talk to Qdrant itself.

    The encoder is lazy-loaded on first use to keep import time fast.

    Parameters
    ──────────
    model_name :
        Any HuggingFace encoder model. The last hidden states of all non-[PAD]
        tokens are used as per-token embeddings.
    device :
        "cuda", "cpu", or None (auto-detect).
    query_prefix :
        Optional prefix prepended to queries at encode time (ColBERT style).
        For mmlw-v2 use "[query]: "; for colbertv2.0 use "[Q] ".
    doc_prefix :
        Optional prefix for documents. ColBERT v2 uses "[D] ".
    normalize :
        L2-normalise token vectors before MaxSim (recommended).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: str | None = None,
        query_prefix: str = "[query]: ",
        doc_prefix: str = "",
        normalize: bool = True,
        max_query_tokens: int = MAX_QUERY_TOKENS,
        max_doc_tokens: int = MAX_DOC_TOKENS,
    ) -> None:
        self.model_name = model_name
        self.device_name = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        self.normalize = normalize
        self.max_query_tokens = max_query_tokens
        self.max_doc_tokens = max_doc_tokens

        self._tokenizer: AutoTokenizer | None = None
        self._model: AutoModel | None = None

    # ── lazy model loading ────────────────────────────────────────────────────

    @property
    def tokenizer(self) -> AutoTokenizer:
        if self._tokenizer is None:
            log.info("Loading ColBERT tokenizer '%s' …", self.model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        return self._tokenizer

    @property
    def model(self) -> AutoModel:
        if self._model is None:
            log.info("Loading ColBERT model '%s' on %s …", self.model_name, self.device_name)
            self._model = AutoModel.from_pretrained(self.model_name)
            self._model.eval()
            self._model.to(self.device_name)
        return self._model

    @property
    def device(self) -> torch.device:
        return torch.device(self.device_name)

    # ── encoding ─────────────────────────────────────────────────────────────

    def _encode_texts(
        self,
        texts: list[str],
        max_length: int,
        prefix: str,
    ) -> list[np.ndarray]:
        """
        Encode a batch of texts into per-token embedding matrices.

        Returns list of np.ndarray, each shaped (n_tokens, hidden_dim), where
        n_tokens varies per text (padding tokens are dropped).
        """
        prefixed = [(prefix + t) if prefix else t for t in texts]
        encoding = self.tokenizer(
            prefixed,
            max_length=max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        input_ids = encoding["input_ids"].to(self.device)
        attention_mask = encoding["attention_mask"].to(self.device)

        with torch.no_grad():
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            # Use last hidden state — shape: (batch, seq_len, hidden_dim)
            hidden = outputs.last_hidden_state  # (B, L, H)

        results = []
        for i in range(hidden.size(0)):
            mask_i = attention_mask[i].bool()
            token_vecs = hidden[i][mask_i]          # (n_valid_tokens, H)
            vecs = token_vecs.cpu().float().numpy()
            if self.normalize:
                vecs = _l2_normalize(vecs)
            results.append(vecs)

        return results

    def encode_query(self, text: str) -> np.ndarray:
        """
        Encode a single query into a per-token embedding matrix.

        Returns np.ndarray of shape (n_query_tokens, hidden_dim).
        """
        result = self._encode_texts([text], self.max_query_tokens, self.query_prefix)
        return result[0]

    def encode_documents(self, texts: list[str]) -> list[np.ndarray]:
        """
        Encode a list of document texts into per-token embedding matrices.

        Returns list of np.ndarray, each (n_doc_tokens_i, hidden_dim).
        Processed in mini-batches for memory efficiency.
        """
        all_vecs: list[np.ndarray] = []
        batch_size = DEFAULT_BATCH_SIZE
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vecs = self._encode_texts(batch, self.max_doc_tokens, self.doc_prefix)
            all_vecs.extend(vecs)
        return all_vecs

    # ── scoring ───────────────────────────────────────────────────────────────

    def maxsim_score(self, query_vecs: np.ndarray, doc_vecs: np.ndarray) -> float:
        """
        Compute ColBERT MaxSim score between a query and a single document.

        MaxSim(q, d) = Σ_{i ∈ Q} max_{j ∈ D} cos_sim(q_i, d_j)

        When vectors are L2-normalised (default), the dot product equals cosine sim.

        Parameters
        ──────────
        query_vecs : np.ndarray (n_query_tokens, dim)
        doc_vecs   : np.ndarray (n_doc_tokens, dim)

        Returns
        ───────
        float — sum of per-query-token max similarities
        """
        if query_vecs.shape[0] == 0 or doc_vecs.shape[0] == 0:
            return 0.0
        # (n_q, dim) × (dim, n_d) → (n_q, n_d)
        sim_matrix = query_vecs @ doc_vecs.T
        # For each query token, find max similarity across all doc tokens
        per_token_max = sim_matrix.max(axis=1)   # (n_q,)
        return float(per_token_max.sum())

    def maxsim_scores_batch(
        self,
        query_vecs: np.ndarray,
        doc_vecs_list: list[np.ndarray],
    ) -> list[float]:
        """
        Compute MaxSim score of one query against a list of documents.

        Slightly more efficient than calling maxsim_score in a loop since the
        query matrix is only held once.
        """
        return [self.maxsim_score(query_vecs, dv) for dv in doc_vecs_list]

    # ── reranking interface ───────────────────────────────────────────────────

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """
        Rerank *candidates* using ColBERT MaxSim and return the top *top_k*.

        This is the primary integration point with LegalRetriever.
        The chunk.score field is updated in-place with the MaxSim score.

        Parameters
        ──────────
        query      : original user query (str)
        candidates : list of RetrievedChunk objects from prior retrieval step
        top_k      : number of results to return

        Returns
        ───────
        list[RetrievedChunk] — reranked, score updated, length ≤ top_k
        """
        if not candidates:
            return candidates

        log.debug("ColBERT reranking %d candidates (top_k=%d) …", len(candidates), top_k)

        # Encode query once
        query_vecs = self.encode_query(query)   # (n_q, dim)

        # Encode all candidate texts (use parent_text when available for richer context)
        doc_texts = [
            c.parent_text if c.parent_text else c.text
            for c in candidates
        ]
        doc_vecs_list = self.encode_documents(doc_texts)

        # Score and sort
        scores = self.maxsim_scores_batch(query_vecs, doc_vecs_list)
        ranked = sorted(
            zip(scores, candidates),
            key=lambda x: x[0],
            reverse=True,
        )

        results = []
        for colbert_score, chunk in ranked[:top_k]:
            chunk.score = round(float(colbert_score), 4)
            results.append(chunk)

        log.debug(
            "ColBERT rerank done. Top score: %.4f | Bottom: %.4f",
            results[0].score if results else 0.0,
            results[-1].score if results else 0.0,
        )
        return results


# ── index builder ─────────────────────────────────────────────────────────────


@dataclass
class _ChunkMeta:
    """Lightweight metadata record stored in the index manifest."""
    chunk_idx: int        # position in the flat token array
    n_tokens: int         # number of token vectors for this chunk
    act_id: str
    title: str
    year: str
    publisher: str
    pos: str
    url: str
    chunk_index: int
    total_chunks: int
    text_preview: str     # first 200 chars for display


class ColBERTIndexBuilder:
    """
    Build and search a token-level ColBERT index over chunks.jsonl.

    The index is a flat array of normalised token vectors stored as memory-mapped
    numpy arrays on disk, partitioned into shards of SHARD_SIZE chunks each.

    Index layout (all inside *index_dir*):
      manifest.jsonl  — one JSON object per chunk with metadata + offset info
      shard_NNNN.npy  — float32 array shape (total_tokens_in_shard, dim)

    Search uses brute-force MaxSim over all stored doc token vectors. For corpora
    up to ~100k chunks at 256 tokens each this is tractable in RAM (≈ 6 GB for
    dim=1024). For larger corpora, switch to FAISS IVF on the flattened token store.

    Parameters
    ──────────
    retriever    : ColBERTRetriever instance (encoder)
    index_dir    : directory for index files
    shard_size   : number of chunks per shard file
    """

    def __init__(
        self,
        retriever: ColBERTRetriever | None = None,
        index_dir: Path = DEFAULT_INDEX_DIR,
        shard_size: int = SHARD_SIZE,
    ) -> None:
        self.retriever = retriever or ColBERTRetriever()
        self.index_dir = Path(index_dir)
        self.shard_size = shard_size

        # Loaded at search time
        self._meta: list[_ChunkMeta] = []
        self._shards: list[np.ndarray] = []   # list of (total_tokens, dim) arrays
        self._loaded: bool = False

    # ── building ──────────────────────────────────────────────────────────────

    def build(self, chunks_path: Path, max_chunks: int | None = None) -> None:
        """
        Build the ColBERT token index from *chunks_path* (JSONL).

        Encodes each chunk's text and writes token vectors + metadata to disk.
        Existing index files in index_dir are overwritten.
        """
        if not chunks_path.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

        self.index_dir.mkdir(parents=True, exist_ok=True)

        log.info("Loading chunks from %s …", chunks_path)
        chunks: list[dict] = []
        with chunks_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if max_chunks and len(chunks) >= max_chunks:
                    break

        log.info("Encoding %d chunks with ColBERT model …", len(chunks))

        manifest_path = self.index_dir / "manifest.jsonl"
        manifest_fh = manifest_path.open("w", encoding="utf-8")

        global_chunk_idx = 0
        shard_idx = 0
        shard_vectors: list[np.ndarray] = []   # accumulate token vecs for current shard
        shard_token_count = 0
        chunks_in_shard = 0

        def _flush_shard(vectors: list[np.ndarray], idx: int) -> None:
            if not vectors:
                return
            arr = np.concatenate(vectors, axis=0).astype(np.float32)
            shard_file = self.index_dir / f"shard_{idx:04d}.npy"
            np.save(str(shard_file), arr)
            log.info(
                "Shard %04d written: %d token vectors (shape %s) → %s",
                idx, arr.shape[0], arr.shape, shard_file.name,
            )

        batch_texts: list[str] = []
        batch_meta_buf: list[dict] = []
        encode_batch = DEFAULT_BATCH_SIZE

        def _process_batch(texts: list[str], metas: list[dict]) -> None:
            nonlocal global_chunk_idx, shard_idx, shard_token_count, chunks_in_shard
            nonlocal shard_vectors

            doc_vecs_list = self.retriever.encode_documents(texts)

            for vecs, meta in zip(doc_vecs_list, metas):
                # Record metadata with shard/offset info
                chunk_record = _ChunkMeta(
                    chunk_idx=global_chunk_idx,
                    n_tokens=vecs.shape[0],
                    act_id=meta["act_id"],
                    title=meta["title"],
                    year=str(meta["year"]),
                    publisher=meta["publisher"],
                    pos=str(meta["pos"]),
                    url=meta["url"],
                    chunk_index=int(meta["chunk_index"]),
                    total_chunks=int(meta["total_chunks"]),
                    text_preview=meta["text"][:200],
                )
                # Write manifest entry with shard info
                manifest_entry = {
                    **chunk_record.__dict__,
                    "shard": shard_idx,
                    "token_offset": shard_token_count,
                }
                manifest_fh.write(json.dumps(manifest_entry, ensure_ascii=False) + "\n")

                shard_vectors.append(vecs)
                shard_token_count += vecs.shape[0]
                chunks_in_shard += 1
                global_chunk_idx += 1

                # Flush shard when it hits size limit
                if chunks_in_shard >= self.shard_size:
                    _flush_shard(shard_vectors, shard_idx)
                    shard_idx += 1
                    shard_vectors = []
                    shard_token_count = 0
                    chunks_in_shard = 0

        for chunk in chunks:
            text = chunk.get("text", "")
            if not text.strip():
                continue
            batch_texts.append(text)
            batch_meta_buf.append({
                "act_id": chunk.get("act_id", ""),
                "title": chunk.get("title", ""),
                "year": chunk.get("year", ""),
                "publisher": chunk.get("publisher", "WDU"),
                "pos": chunk.get("pos", ""),
                "url": chunk.get("url", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "total_chunks": chunk.get("total_chunks", 1),
                "text": text,
            })
            if len(batch_texts) >= encode_batch:
                _process_batch(batch_texts, batch_meta_buf)
                batch_texts = []
                batch_meta_buf = []

        # Flush remaining
        if batch_texts:
            _process_batch(batch_texts, batch_meta_buf)
        if shard_vectors:
            _flush_shard(shard_vectors, shard_idx)

        manifest_fh.close()

        # Write index metadata
        index_meta = {
            "model": self.retriever.model_name,
            "total_chunks": global_chunk_idx,
            "n_shards": shard_idx + 1 if shard_vectors or global_chunk_idx > 0 else shard_idx,
            "dim": (
                shard_vectors[0].shape[1] if shard_vectors
                else self.retriever._model.config.hidden_size
                if self.retriever._model else 0
            ),
            "max_doc_tokens": self.retriever.max_doc_tokens,
            "normalize": self.retriever.normalize,
        }
        (self.index_dir / "index_meta.json").write_text(
            json.dumps(index_meta, indent=2), encoding="utf-8"
        )
        log.info(
            "ColBERT index built: %d chunks, %d shards → %s",
            global_chunk_idx, index_meta["n_shards"], self.index_dir,
        )

    # ── loading ───────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Load the index from disk into memory (memory-mapped for large corpora)."""
        meta_file = self.index_dir / "index_meta.json"
        manifest_file = self.index_dir / "manifest.jsonl"
        if not meta_file.exists() or not manifest_file.exists():
            raise FileNotFoundError(
                f"ColBERT index not found in {self.index_dir}. "
                "Run build() first."
            )

        index_meta = json.loads(meta_file.read_text(encoding="utf-8"))
        n_shards = index_meta.get("n_shards", 0)
        log.info(
            "Loading ColBERT index: %d chunks across %d shards …",
            index_meta.get("total_chunks", "?"),
            n_shards,
        )

        # Load shard arrays (memory-mapped — OS will swap as needed)
        self._shards = []
        for i in range(n_shards):
            shard_file = self.index_dir / f"shard_{i:04d}.npy"
            if shard_file.exists():
                arr = np.load(str(shard_file), mmap_mode="r")
                self._shards.append(arr)
            else:
                log.warning("Missing shard file: %s", shard_file)

        # Load manifest
        self._meta = []
        with manifest_file.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    self._meta.append(_ChunkMeta(
                        chunk_idx=d["chunk_idx"],
                        n_tokens=d["n_tokens"],
                        act_id=d["act_id"],
                        title=d["title"],
                        year=d["year"],
                        publisher=d["publisher"],
                        pos=d["pos"],
                        url=d["url"],
                        chunk_index=d["chunk_index"],
                        total_chunks=d["total_chunks"],
                        text_preview=d["text_preview"],
                    ))
                except (json.JSONDecodeError, KeyError) as exc:
                    log.warning("Skipping bad manifest line: %s", exc)

        self._loaded = True
        log.info("Index loaded: %d chunks, %d shards", len(self._meta), len(self._shards))

    # ── search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        publisher_filter: str | None = None,
    ) -> list[dict]:
        """
        Approximate MaxSim search over the full indexed corpus.

        This is an exhaustive scan — suitable for dev/eval or smaller corpora.
        For production over 100k+ docs, integrate FAISS IVF over the token store.

        Parameters
        ──────────
        query            : user question (Polish)
        top_k            : number of results to return
        publisher_filter : optional publisher restriction (e.g. "WDU")

        Returns
        ───────
        list of dicts with keys: score, act_id, title, year, publisher, url,
                                  chunk_index, text_preview
        """
        if not self._loaded:
            self.load()

        query_vecs = self.retriever.encode_query(query)   # (n_q, dim)

        # Build a dict mapping shard_idx → list of (meta, token_offset_in_shard, n_tokens)
        # so we can vectorise the MaxSim computation per shard
        from collections import defaultdict
        shard_chunks: dict[int, list[tuple[_ChunkMeta, int]]] = defaultdict(list)

        # Read per-chunk shard offsets from manifest
        manifest_file = self.index_dir / "manifest.jsonl"
        with manifest_file.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if publisher_filter and d.get("publisher") != publisher_filter:
                        continue
                    shard = d.get("shard", 0)
                    offset = d.get("token_offset", 0)
                    n_tokens = d.get("n_tokens", 0)
                    chunk_idx = d.get("chunk_idx", 0)
                    if chunk_idx < len(self._meta):
                        shard_chunks[shard].append((self._meta[chunk_idx], offset, n_tokens))
                except (json.JSONDecodeError, KeyError):
                    continue

        scores: list[tuple[float, _ChunkMeta]] = []

        for shard_idx, entries in shard_chunks.items():
            if shard_idx >= len(self._shards):
                continue
            shard_arr = self._shards[shard_idx]    # (total_shard_tokens, dim)

            # Compute all similarities at once: (n_q, total_shard_tokens)
            sim_matrix = query_vecs @ shard_arr.T   # (n_q, total_shard_tokens)

            for meta, offset, n_tokens in entries:
                if n_tokens == 0:
                    continue
                end = offset + n_tokens
                # Slice sim matrix for this chunk's token columns
                chunk_sims = sim_matrix[:, offset:end]   # (n_q, n_doc_tokens)
                per_q_max = chunk_sims.max(axis=1)       # (n_q,)
                score = float(per_q_max.sum())
                scores.append((score, meta))

        scores.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, meta in scores[:top_k]:
            results.append({
                "score": round(score, 4),
                "act_id": meta.act_id,
                "title": meta.title,
                "year": meta.year,
                "publisher": meta.publisher,
                "url": meta.url,
                "chunk_index": meta.chunk_index,
                "total_chunks": meta.total_chunks,
                "text_preview": meta.text_preview,
            })
        return results


# ── LegalRetriever integration patch ─────────────────────────────────────────
#
# To enable ColBERT reranking in LegalRetriever, apply the following patch to
# rag/retriever.py (or use the ColBERTRetriever.rerank() method directly after
# calling LegalRetriever.retrieve()):
#
#   In __init__, add parameter:
#       colbert_reranker: ColBERTRetriever | None = None
#   In retrieve(), after the cross-encoder reranking block, add:
#       if self.colbert_reranker is not None:
#           results = self.colbert_reranker.rerank(query, results, top_k)
#
# This file also provides a standalone integration function for convenience:


def apply_colbert_rerank(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int,
    model_name: str = DEFAULT_MODEL,
    device: str | None = None,
) -> list[RetrievedChunk]:
    """
    Convenience function: apply ColBERT reranking to an existing list of
    RetrievedChunk objects without constructing a ColBERTRetriever manually.

    Useful for one-off reranking or testing from the REPL.
    """
    reranker = ColBERTRetriever(model_name=model_name, device=device)
    return reranker.rerank(query, candidates, top_k)


# ── CLI ───────────────────────────────────────────────────────────────────────


def _demo_rerank(query: str, qdrant_path: str, top_k: int = 5) -> None:
    """Run a live demo: retrieve from Qdrant, then rerank with ColBERT."""
    try:
        from rag.retriever import LegalRetriever
    except ImportError as exc:
        log.error("Cannot import LegalRetriever: %s", exc)
        return

    log.info("Running demo rerank for: %s", query)

    # Standard hybrid retrieval (no reranking — fetch more candidates for ColBERT)
    retriever = LegalRetriever(qdrant=qdrant_path, rerank=False)
    candidates = retriever.retrieve(query, top_k=top_k * 4, expand=False)
    log.info("Retrieved %d candidates from Qdrant", len(candidates))

    colbert = ColBERTRetriever()
    reranked = colbert.rerank(query, candidates, top_k)

    print(f"\nQuery: {query}")
    print(f"ColBERT top-{top_k} results:\n")
    for i, chunk in enumerate(reranked, 1):
        print(f"[{i}] Score: {chunk.score:.4f} | {chunk.citation()}")
        print(f"     {chunk.text[:280]}{'…' if len(chunk.text) > 280 else ''}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "ColBERT late-interaction retrieval for Polish legal text.\n\n"
            "Build an index:\n"
            "  python rag/colbert_retriever.py "
            "--build data/processed/chunks.jsonl --index-dir data/colbert\n\n"
            "Search the index:\n"
            "  python rag/colbert_retriever.py "
            "--query \"obowiązki pracodawcy\" --index-dir data/colbert --top-k 5\n\n"
            "Rerank demo (requires Qdrant running):\n"
            "  python rag/colbert_retriever.py "
            "--rerank-demo \"Jakie są prawa pracownika?\" --qdrant data/qdrant"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--build", type=Path, default=None, metavar="CHUNKS_JSONL",
        help="Path to chunks.jsonl — build ColBERT index",
    )
    parser.add_argument(
        "--index-dir", type=Path, default=DEFAULT_INDEX_DIR,
        help="Directory for index files (default: data/colbert)",
    )
    parser.add_argument(
        "--query", default=None,
        help="Polish query for index search",
    )
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Number of results to return",
    )
    parser.add_argument(
        "--publisher", default=None,
        help="Filter index search by publisher (e.g. WDU)",
    )
    parser.add_argument(
        "--rerank-demo", default=None, metavar="QUERY",
        help="Run live Qdrant→ColBERT rerank demo for this query",
    )
    parser.add_argument(
        "--qdrant", default="data/qdrant",
        help="Qdrant path or URL (for --rerank-demo)",
    )
    parser.add_argument(
        "--model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL),
        help=f"HuggingFace model for token embeddings (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--device", default=None,
        help="Torch device: 'cuda', 'cpu' (default: auto-detect)",
    )
    parser.add_argument(
        "--max-chunks", type=int, default=None,
        help="Limit number of chunks for index build (for testing)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output search results as JSON",
    )
    args = parser.parse_args()

    # ── Build index ───────────────────────────────────────────────────────────
    if args.build is not None:
        retriever = ColBERTRetriever(model_name=args.model, device=args.device)
        builder = ColBERTIndexBuilder(retriever=retriever, index_dir=args.index_dir)
        builder.build(args.build, max_chunks=args.max_chunks)
        log.info("Index built successfully at %s", args.index_dir)

    # ── Search index ──────────────────────────────────────────────────────────
    elif args.query is not None:
        retriever = ColBERTRetriever(model_name=args.model, device=args.device)
        builder = ColBERTIndexBuilder(retriever=retriever, index_dir=args.index_dir)
        results = builder.search(
            args.query, top_k=args.top_k, publisher_filter=args.publisher
        )
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(f"\nColBERT search results for: {args.query!r}\n")
            for i, r in enumerate(results, 1):
                print(f"[{i}] Score: {r['score']:.4f} | {r['title']} ({r['year']}) poz. {r['pos']}")
                print(f"     {r['text_preview'][:280]}{'…' if len(r['text_preview']) >= 200 else ''}")
                print()

    # ── Live rerank demo ──────────────────────────────────────────────────────
    elif args.rerank_demo is not None:
        _demo_rerank(args.rerank_demo, args.qdrant, top_k=args.top_k)

    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
