"""
raptor.py — RAPTOR hierarchical tree indexing for Polish legal acts.

RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval, ICLR 2024)
builds a multi-level tree over the corpus by recursively clustering chunks and
generating LLM summaries at each level. The result: both leaf-level verbatim
article text AND chapter/act-level summaries are searchable in a single query.

For Polish law this maps naturally:
  Level 0 (leaves): individual article/paragraph chunks (512 tokens)
  Level 1:          chapter summaries (~5-15 articles → 1 summary)
  Level 2 (root):   full act summary (all chapters → 1 summary per ustawa)

Usage (one-time preprocessing, run before ingest):
    python rag/raptor.py \\
        --input data/processed/chunks.jsonl \\
        --output data/processed/chunks_raptor.jsonl \\
        --max-acts 500

Then re-ingest with the RAPTOR-augmented JSONL:
    python rag/ingest.py --input data/processed/chunks_raptor.jsonl --recreate

Requirements:
    pip install scikit-learn openai numpy

Cost estimate: ~$3-5 per 1000 acts with gpt-4o-mini (summary generation).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

MAX_SUMMARY_INPUT_CHARS = 3000   # max text fed to LLM per cluster
MAX_CLUSTER_SIZE = 15            # max chunks per cluster before splitting
MIN_CLUSTER_SIZE = 3             # min chunks per cluster for summarization
SUMMARY_MAX_TOKENS = 300         # max tokens for each LLM-generated summary


def _summarize_cluster(
    texts: list[str],
    meta: dict,
    client,
    model: str,
    level: int,
) -> str:
    """Call LLM to summarize a cluster of chunks into a single paragraph."""
    combined = "\n\n---\n\n".join(texts)[:MAX_SUMMARY_INPUT_CHARS]
    act_title = meta.get("title", "")
    pub = meta.get("publisher", "")

    if pub in ("ADMINISTRATIVE", "SUPREME", "CONSTITUTIONAL_TRIBUNAL", "COMMON", "NATIONAL_APPEAL_CHAMBER"):
        system = (
            "Jesteś asystentem prawnym. Napisz zwięzłe streszczenie (3-5 zdań) "
            "poniższych fragmentów wyroku sądowego. Zachowaj kluczowe tezy prawne, "
            "podstawę prawną i wynik sprawy. Pisz po polsku."
        )
    else:
        system = (
            "Jesteś asystentem prawnym. Napisz zwięzłe streszczenie (3-5 zdań) "
            f"poniższych fragmentów {'ustawy' if level == 1 else 'rozdziału'}: "
            f"'{act_title}'. Zachowaj kluczowe obowiązki, prawa, definicje i terminy. "
            "Pisz po polsku w stylu prawniczym."
        )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": combined},
            ],
            temperature=0.0,
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log.warning("Summary generation failed: %s", exc)
        return combined[:500] + "…"


def _cluster_by_article_sections(chunks: list[dict]) -> list[list[dict]]:
    """
    Cluster chunks by article boundaries using the article detection already in preprocess.py.
    Chunks from the same article group stay together. Falls back to size-based batching.
    """
    import re
    article_re = re.compile(r"^(?:Art\.|Artykuł|§)\s*\d+", re.IGNORECASE | re.MULTILINE)

    clusters: list[list[dict]] = []
    current: list[dict] = []

    for chunk in chunks:
        text = chunk.get("text", "")
        # Start a new cluster if this chunk begins a new article AND current is large enough
        if article_re.match(text.strip()) and len(current) >= MIN_CLUSTER_SIZE:
            clusters.append(current)
            current = [chunk]
        else:
            current.append(chunk)
            if len(current) >= MAX_CLUSTER_SIZE:
                clusters.append(current)
                current = []

    if current:
        clusters.append(current)

    # Merge tiny tail clusters into previous
    merged: list[list[dict]] = []
    for cluster in clusters:
        if len(cluster) < MIN_CLUSTER_SIZE and merged:
            merged[-1].extend(cluster)
        else:
            merged.append(cluster)

    return merged if merged else [chunks]


def _make_summary_chunk(
    summary_text: str,
    source_chunks: list[dict],
    level: int,
    cluster_idx: int,
) -> dict:
    """Build a RAPTOR summary chunk that gets added to the index alongside leaves."""
    first = source_chunks[0]
    return {
        "act_id": first.get("act_id", ""),
        "title": first.get("title", ""),
        "year": first.get("year", ""),
        "publisher": first.get("publisher", "WDU"),
        "pos": first.get("pos", ""),
        "url": first.get("url", ""),
        "status": first.get("status", ""),
        "chunk_index": 1_000_000 + level * 10_000 + cluster_idx,  # unique index for summaries
        "total_chunks": first.get("total_chunks", 1),
        "text": summary_text,
        "approx_tokens": len(summary_text) // 4,
        "raptor_level": level,
        "raptor_source_chunk_ids": [
            f"{c.get('act_id')}___{c.get('chunk_index', 0)}" for c in source_chunks
        ],
    }


def build_raptor_tree(
    chunks_by_act: dict[str, list[dict]],
    client,
    model: str,
    max_level: int = 2,
) -> list[dict]:
    """
    For each act, build a 2-level RAPTOR tree:
      Level 1: cluster leaf chunks by article → generate chapter summaries
      Level 2: summarize all level-1 summaries → generate act-level summary

    Returns the list of summary chunks to APPEND to the original leaf chunks.
    """
    summary_chunks: list[dict] = []
    total_acts = len(chunks_by_act)

    for act_idx, (act_id, act_chunks) in enumerate(chunks_by_act.items(), 1):
        if not act_chunks:
            continue

        meta = {
            "title": act_chunks[0].get("title", ""),
            "publisher": act_chunks[0].get("publisher", "WDU"),
        }

        log.info("[%d/%d] Building RAPTOR tree for %s (%d chunks) …",
                 act_idx, total_acts, act_id[:60], len(act_chunks))

        level1_summaries: list[dict] = []

        if len(act_chunks) >= MIN_CLUSTER_SIZE:
            clusters = _cluster_by_article_sections(act_chunks)
            for c_idx, cluster in enumerate(clusters):
                texts = [c.get("text", "") for c in cluster]
                summary = _summarize_cluster(texts, meta, client, model, level=1)
                summary_chunk = _make_summary_chunk(summary, cluster, level=1, cluster_idx=c_idx)
                summary_chunks.append(summary_chunk)
                level1_summaries.append(summary_chunk)

        # Level 2: summarize all level-1 summaries → full act summary
        if max_level >= 2 and len(level1_summaries) >= 2:
            all_summaries = [c["text"] for c in level1_summaries]
            act_summary = _summarize_cluster(all_summaries, meta, client, model, level=2)
            act_summary_chunk = _make_summary_chunk(
                act_summary, act_chunks, level=2, cluster_idx=0
            )
            summary_chunks.append(act_summary_chunk)

        time.sleep(0.05)  # gentle rate limiting

    return summary_chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build RAPTOR hierarchical summaries over the legal corpus."
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/chunks_raptor.jsonl"))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-acts", type=int, default=None, help="Limit number of acts (for testing)")
    parser.add_argument("--max-level", type=int, default=2, help="Maximum RAPTOR tree depth (1 or 2)")
    parser.add_argument("--isap-only", action="store_true", help="Build tree only for ISAP legislation")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without generating summaries")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        log.error("OPENAI_API_KEY not set")
        sys.exit(1)

    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        sys.exit(1)

    log.info("Loading chunks from %s …", args.input)
    all_chunks: list[dict] = []
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    all_chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    log.info("Loaded %d chunks", len(all_chunks))

    SAOS_PUBLISHERS = {"ADMINISTRATIVE", "SUPREME", "CONSTITUTIONAL_TRIBUNAL", "COMMON", "NATIONAL_APPEAL_CHAMBER"}
    if args.isap_only:
        all_chunks = [c for c in all_chunks if c.get("publisher", "WDU") not in SAOS_PUBLISHERS]
        log.info("Filtered to ISAP-only: %d chunks", len(all_chunks))

    # Group by act_id
    chunks_by_act: dict[str, list[dict]] = defaultdict(list)
    for chunk in all_chunks:
        chunks_by_act[chunk.get("act_id", "unknown")].append(chunk)

    act_ids = list(chunks_by_act.keys())
    if args.max_acts:
        act_ids = act_ids[: args.max_acts]
        chunks_by_act = {k: chunks_by_act[k] for k in act_ids}

    log.info("Acts to process: %d", len(chunks_by_act))

    if args.dry_run:
        total_clusters = sum(
            len(_cluster_by_article_sections(chunks))
            for chunks in chunks_by_act.values()
            if len(chunks) >= MIN_CLUSTER_SIZE
        )
        log.info(
            "DRY RUN stats: %d acts → estimated %d L1 clusters → %d L1+L2 summaries",
            len(chunks_by_act), total_clusters,
            total_clusters + sum(1 for v in chunks_by_act.values() if len(v) >= MIN_CLUSTER_SIZE),
        )
        log.info(
            "Estimated cost: ~$%.2f (gpt-4o-mini, %d LLM calls)",
            total_clusters * 2 * 0.00015,
            total_clusters * 2,
        )
        return

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    log.info("Building RAPTOR tree (max_level=%d) …", args.max_level)
    summary_chunks = build_raptor_tree(chunks_by_act, client, args.model, args.max_level)
    log.info("Generated %d summary chunks", len(summary_chunks))

    # Write original leaves + summary nodes
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as fout:
        for chunk in all_chunks:
            fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            written += 1
        for chunk in summary_chunks:
            fout.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            written += 1

    log.info(
        "Done. Written %d chunks (%d original + %d RAPTOR summaries) to %s",
        written, len(all_chunks), len(summary_chunks), args.output,
    )
    log.info(
        "Next step: rm data/qdrant/.ingested && "
        "python rag/ingest.py --input %s --recreate",
        args.output,
    )


if __name__ == "__main__":
    main()
