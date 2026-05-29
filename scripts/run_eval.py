"""
run_eval.py — Run RAG evaluation on the golden question set.

For each question in eval_questions.jsonl:
  1. Retrieve top-k chunks from Qdrant (RAG)
  2. Optionally call Claude to generate an answer
  3. Score: citation hit rate, key fact coverage, retrieval score

Usage:
    python scripts/run_eval.py
    python scripts/run_eval.py --no-llm          # retrieval quality only
    python scripts/run_eval.py --output results/eval_2024.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_questions(path: Path) -> list[dict]:
    questions = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def score_retrieval(chunks: list, question: dict) -> dict:
    """Score how well retrieved chunks cover the expected facts."""
    if not chunks:
        return {"retrieval_top_score": 0.0, "keyword_hits": 0, "keyword_total": 0, "keyword_rate": 0.0}

    top_score = chunks[0].score
    all_text = " ".join(c.text.lower() for c in chunks)
    all_text += " ".join(c.title.lower() for c in chunks)

    keywords = question.get("expected_act_keywords", [])
    hits = sum(1 for kw in keywords if kw.lower() in all_text)

    return {
        "retrieval_top_score": round(top_score, 4),
        "keyword_hits": hits,
        "keyword_total": len(keywords),
        "keyword_rate": round(hits / len(keywords), 3) if keywords else 1.0,
    }


def score_answer(answer: str, question: dict) -> dict:
    """Score how well the LLM answer covers the key facts."""
    key_facts = question.get("key_facts", [])
    if not key_facts:
        return {"fact_hits": 0, "fact_total": 0, "fact_rate": 1.0}

    answer_lower = answer.lower()
    hits = sum(1 for fact in key_facts if fact.lower() in answer_lower)
    return {
        "fact_hits": hits,
        "fact_total": len(key_facts),
        "fact_rate": round(hits / len(key_facts), 3),
    }


def call_openai(question: str, context: str, api_key: str, model: str = "gpt-4o") -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    system = (
        "Jesteś ekspertem ds. polskiego prawa. Odpowiadasz zwięźle i precyzyjnie po polsku. "
        "Powołujesz się na konkretne artykuły i akty prawne z podanego kontekstu."
    )
    prompt = (
        f"Na podstawie poniższych przepisów prawnych, odpowiedz na pytanie.\n\n"
        f"PRZEPISY:\n{context}\n\n"
        f"PYTANIE: {question}\n\n"
        f"ODPOWIEDŹ:"
    ) if context else f"PYTANIE: {question}\n\nODPOWIEDŹ:"

    response = client.chat.completions.create(
        model=model,
        max_tokens=512,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LexCorpus RAG evaluation.")
    parser.add_argument("--questions", type=Path, default=Path("data/eval_questions.jsonl"))
    parser.add_argument("--qdrant", default="data/qdrant")
    parser.add_argument("--collection", default="lexcorpus")
    parser.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--no-llm", action="store_true", help="Skip Claude API calls (retrieval scoring only)")
    parser.add_argument("--output", type=Path, default=Path("data/eval_results.json"))
    args = parser.parse_args()

    from rag.retriever import LegalRetriever

    log.info("Loading retriever …")
    retriever = LegalRetriever(qdrant=args.qdrant, collection=args.collection, model_name=args.model)

    questions = load_questions(args.questions)
    log.info("Loaded %d questions", len(questions))

    api_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    use_llm = not args.no_llm and bool(api_key)
    if not use_llm and not args.no_llm:
        log.warning("OPENAI_API_KEY not set — running retrieval-only evaluation")

    results = []
    for q in questions:
        log.info("[%d/%d] %s", q["id"], len(questions), q["question"][:70])

        # Retrieval
        chunks = retriever.retrieve(q["question"], top_k=args.top_k)
        context = retriever.format_context(chunks, max_chars=3000)
        retrieval_scores = score_retrieval(chunks, q)

        # LLM answer
        answer = ""
        answer_scores = {}
        if use_llm:
            try:
                answer = call_openai(q["question"], context, api_key, openai_model)
                answer_scores = score_answer(answer, q)
                time.sleep(0.5)  # gentle rate limit
            except Exception as exc:
                log.warning("Claude call failed for q%d: %s", q["id"], exc)
                answer = f"[ERROR: {exc}]"

        result = {
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "answer": answer,
            "sources": [
                {"score": c.score, "title": c.title[:80], "year": c.year, "text": c.text[:200]}
                for c in chunks
            ],
            **retrieval_scores,
            **answer_scores,
        }
        results.append(result)

        # Print live result
        print(f"\n{'='*70}")
        print(f"Q{q['id']} [{q['category']}]: {q['question']}")
        print(f"  Retrieval: top_score={retrieval_scores['retrieval_top_score']:.3f}  keywords={retrieval_scores['keyword_hits']}/{retrieval_scores['keyword_total']} ({retrieval_scores['keyword_rate']:.0%})")
        if chunks:
            print(f"  Best source: {chunks[0].title[:65]}")
        if answer:
            print(f"  Answer: {answer[:200]}")
            print(f"  Key facts: {answer_scores.get('fact_hits',0)}/{answer_scores.get('fact_total',0)} ({answer_scores.get('fact_rate',0):.0%})")

    # Aggregate stats
    avg_retrieval = sum(r["retrieval_top_score"] for r in results) / len(results)
    avg_keyword = sum(r["keyword_rate"] for r in results) / len(results)

    summary = {
        "n_questions": len(results),
        "llm_used": use_llm,
        "avg_retrieval_score": round(avg_retrieval, 4),
        "avg_keyword_rate": round(avg_keyword, 4),
    }
    if use_llm:
        answered = [r for r in results if r.get("fact_rate") is not None]
        if answered:
            summary["avg_fact_rate"] = round(sum(r["fact_rate"] for r in answered) / len(answered), 4)

    print(f"\n{'='*70}")
    print("SUMMARY")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    output = {"summary": summary, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
