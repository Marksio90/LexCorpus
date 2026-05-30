"""
self_rag_prepare.py — Prepare Self-RAG training data for Bielik-7B/11B.

Self-RAG (Asai et al., ICLR 2024) trains the LLM to generate special reflection
tokens that decide whether retrieval is needed and whether retrieved docs are relevant:

  [Retrieve]   — should I retrieve? (yes/no)
  [IsREL]      — is this passage relevant? (relevant/irrelevant)
  [IsSUP]      — does the passage support the answer? (fully/partially/no)
  [IsUSE]      — is this response useful? (5/4/3/2/1)

This script converts existing QA pairs from data/dataset/synthetic/train.jsonl into
Self-RAG format by:
1. Marking every answer with a [Retrieve] decision
2. For each retrieved passage, adding [IsREL] and [IsSUP] tokens
3. Adding [IsUSE] score at end of each response segment

Output format (chat JSONL compatible with training/self_rag_train.py):
    {
      "messages": [
        {"role": "user", "content": "Jakie są okresy wypowiedzenia umowy o pracę?"},
        {"role": "assistant", "content":
          "[Retrieve]Tak[IsREL]istotne[Passage]Art. 36 KP ... [/Passage]"
          "[IsSUP]w pełni Okresy wypowiedzenia wynoszą ... [IsUSE]5"}
      ]
    }

Usage:
    python training/self_rag_prepare.py \\
        --qa-input data/dataset/synthetic/train.jsonl \\
        --chunks data/processed/chunks.jsonl \\
        --output data/dataset/self_rag/train.jsonl \\
        --max-examples 10000

Requirements:
    No external deps (pure Python). Optional: openai for GPT-4o-mini relevance scoring.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Self-RAG special tokens
TOK_RETRIEVE_YES   = "[Retrieve]Tak"
TOK_RETRIEVE_NO    = "[Retrieve]Nie"
TOK_RELEVANT       = "[IsREL]istotne"
TOK_IRRELEVANT     = "[IsREL]nieistotne"
TOK_SUPPORTS_FULL  = "[IsSUP]w pełni"
TOK_SUPPORTS_PART  = "[IsSUP]częściowo"
TOK_SUPPORTS_NO    = "[IsSUP]nie"
TOK_USE_PREFIX     = "[IsUSE]"

PASSAGE_OPEN  = "[Passage]"
PASSAGE_CLOSE = "[/Passage]"

POLISH_LEGAL_STOP_WORDS = {
    "co", "to", "jest", "jak", "który", "która", "które", "oraz",
    "przez", "przy", "dla", "lub", "albo", "czy", "nie", "się",
}


def _keyword_overlap(question: str, text: str) -> float:
    """Simple relevance heuristic: word overlap between question and passage."""
    q_words = {w.lower() for w in question.split() if len(w) > 3 and w.lower() not in POLISH_LEGAL_STOP_WORDS}
    p_words = {w.lower() for w in text.split() if len(w) > 3}
    if not q_words:
        return 0.0
    return len(q_words & p_words) / len(q_words)


def _find_relevant_chunks(question: str, answer: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    """Find chunks most relevant to this QA pair using keyword overlap."""
    scored = []
    for chunk in chunks:
        text = chunk.get("text", "")
        score = _keyword_overlap(question + " " + answer, text)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _format_self_rag_response(
    answer: str,
    relevant_chunks: list[dict],
    question: str,
) -> str:
    """
    Build a Self-RAG formatted assistant turn.

    Structure (per retrieved passage):
      [Retrieve]Tak[IsREL]istotne[Passage]...[/Passage][IsSUP]w pełni <answer_segment>[IsUSE]5
    """
    if not relevant_chunks:
        # No retrieval needed (trivial question)
        return f"{TOK_RETRIEVE_NO}{answer}[IsUSE]4"

    parts = []
    answer_words = answer.split()
    # Split answer into segments (one per passage)
    seg_size = max(1, len(answer_words) // len(relevant_chunks))

    for i, chunk in enumerate(relevant_chunks):
        passage_text = chunk.get("text", "")[:400].replace("\n", " ")
        relevance = _keyword_overlap(question, passage_text)

        is_rel = TOK_RELEVANT if relevance > 0.1 else TOK_IRRELEVANT
        is_sup = TOK_SUPPORTS_FULL if relevance > 0.3 else (TOK_SUPPORTS_PART if relevance > 0.1 else TOK_SUPPORTS_NO)

        # Assign an answer segment to this passage
        seg_start = i * seg_size
        seg_end = (i + 1) * seg_size if i < len(relevant_chunks) - 1 else len(answer_words)
        answer_segment = " ".join(answer_words[seg_start:seg_end])

        is_use_score = "5" if relevance > 0.3 else ("4" if relevance > 0.1 else "3")
        part = (
            f"{TOK_RETRIEVE_YES}{is_rel}"
            f"{PASSAGE_OPEN}{passage_text}{PASSAGE_CLOSE}"
            f"{is_sup} {answer_segment}{TOK_USE_PREFIX}{is_use_score}"
        )
        parts.append(part)

    return "".join(parts)


def _load_qa_pairs(path: Path) -> list[dict]:
    pairs = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Support both chat-format and legacy instruction-format
            if "messages" in obj:
                msgs = obj["messages"]
                user_msg = next((m["content"] for m in msgs if m["role"] == "user"), "")
                asst_msg = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
                if user_msg and asst_msg:
                    pairs.append({"question": user_msg, "answer": asst_msg})
            elif "instruction" in obj and "output" in obj:
                pairs.append({"question": obj["instruction"], "answer": obj["output"]})
    return pairs


def _load_chunks(path: Path, max_chunks: int = 50000) -> list[dict]:
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chunks.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            if len(chunks) >= max_chunks:
                break
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare Self-RAG training data for Bielik from QA pairs + chunks."
    )
    parser.add_argument("--qa-input", type=Path, default=Path("data/dataset/synthetic/train.jsonl"),
                        help="QA pairs (chat or instruction format JSONL)")
    parser.add_argument("--chunks", type=Path, default=Path("data/processed/chunks.jsonl"),
                        help="Corpus chunks for passage retrieval context")
    parser.add_argument("--output", type=Path, default=Path("data/dataset/self_rag/train.jsonl"))
    parser.add_argument("--max-examples", type=int, default=10000)
    parser.add_argument("--max-chunks", type=int, default=50000,
                        help="Max corpus chunks to keep in memory for relevance scoring")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-retrieval-fraction", type=float, default=0.15,
                        help="Fraction of examples marked as not needing retrieval")
    parser.add_argument("--dry-run", action="store_true", help="Show first 3 formatted examples")
    args = parser.parse_args()

    random.seed(args.seed)

    if not args.qa_input.exists():
        log.error("QA input not found: %s", args.qa_input)
        sys.exit(1)
    if not args.chunks.exists():
        log.error("Chunks not found: %s", args.chunks)
        sys.exit(1)

    log.info("Loading QA pairs from %s …", args.qa_input)
    qa_pairs = _load_qa_pairs(args.qa_input)
    log.info("Loaded %d QA pairs", len(qa_pairs))

    log.info("Loading corpus chunks (max %d) for passage matching …", args.max_chunks)
    chunks = _load_chunks(args.chunks, args.max_chunks)
    log.info("Loaded %d chunks", len(chunks))

    if args.max_examples < len(qa_pairs):
        qa_pairs = random.sample(qa_pairs, args.max_examples)

    if args.dry_run:
        for pair in qa_pairs[:3]:
            rel_chunks = _find_relevant_chunks(pair["question"], pair["answer"], chunks[:1000], top_k=2)
            formatted = _format_self_rag_response(pair["answer"], rel_chunks, pair["question"])
            print(f"\nQ: {pair['question'][:100]}")
            print(f"A (Self-RAG): {formatted[:300]}…")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as fout:
        for i, pair in enumerate(qa_pairs, 1):
            question = pair["question"]
            answer = pair["answer"]

            # Some examples should demonstrate no-retrieval path
            if random.random() < args.no_retrieval_fraction:
                rel_chunks = []
            else:
                rel_chunks = _find_relevant_chunks(question, answer, chunks, top_k=2)

            formatted_answer = _format_self_rag_response(answer, rel_chunks, question)

            record = {
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": formatted_answer},
                ]
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

            if i % 500 == 0:
                log.info("[%d/%d] examples prepared …", i, len(qa_pairs))

    log.info(
        "Done. Written %d Self-RAG examples to %s",
        written, args.output,
    )
    log.info(
        "Next: python training/self_rag_train.py --data %s", args.output
    )


if __name__ == "__main__":
    main()
