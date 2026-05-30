"""
build_eval_benchmark.py — Build a Polish legal QA evaluation benchmark.

Creates eval_questions.jsonl in the GAIus/KIO style: questions from Polish
professional law exams (application, KIO, notarial) with gold answers and
expected source citations. This allows measuring:
  - Retrieval accuracy: was the right statute retrieved?
  - Answer accuracy: does the answer contain the key legal facts?

The script generates synthetic questions from chunks using GPT-4o-mini
(same approach as training data generation but for evaluation).

Usage:
    python scripts/build_eval_benchmark.py \\
        --input data/processed/chunks.jsonl \\
        --output data/eval_questions.jsonl \\
        --n-questions 200 \\
        --categories legislation:100,judgment:60,tax:40

Output format (JSONL):
    {
      "id": 1,
      "category": "legislation",
      "question": "...",
      "expected_act_keywords": ["kodeks pracy", "art. 30"],
      "key_facts": ["wypowiedzenie", "termin wypowiedzenia", "3 miesiące"],
      "source_act_id": "WDU19740240141",
      "difficulty": "medium"
    }
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SAOS_PUBLISHERS = frozenset(
    {"ADMINISTRATIVE", "SUPREME", "CONSTITUTIONAL_TRIBUNAL", "COMMON", "NATIONAL_APPEAL_CHAMBER"}
)

CATEGORY_MAP = {
    "legislation": lambda c: c.get("publisher", "WDU") not in SAOS_PUBLISHERS and c.get("publisher") != "KIS",
    "judgment":    lambda c: c.get("publisher", "WDU") in SAOS_PUBLISHERS,
    "tax":         lambda c: c.get("publisher") == "KIS",
}

SYSTEM_QUESTION_GEN = (
    "Jesteś ekspertem ds. polskiego prawa tworzącym pytania egzaminacyjne. "
    "Na podstawie poniższego fragmentu aktu prawnego lub orzeczenia, wygeneruj "
    "jedno trudne pytanie egzaminacyjne (na poziomie aplikacji adwokackiej lub radcowskiej) "
    "oraz podaj:\n"
    "1. Pytanie (w języku polskim)\n"
    "2. Kluczowe fakty prawne które powinna zawierać prawidłowa odpowiedź (lista, po 1 na linię, prefix: FAKT:)\n"
    "3. Słowa kluczowe identyfikujące źródło (ustawa/artykuł) (lista, po 1 na linię, prefix: KLUCZOWE:)\n"
    "4. Trudność: łatwe/średnie/trudne\n\n"
    "Format odpowiedzi:\n"
    "PYTANIE: ...\n"
    "FAKT: ...\nFAKT: ...\n"
    "KLUCZOWE: ...\nKLUCZOWE: ...\n"
    "TRUDNOŚĆ: ...\n"
)


def _parse_question_response(response_text: str, chunk: dict, question_id: int) -> dict | None:
    """Parse the structured LLM response into eval question format."""
    lines = response_text.strip().splitlines()
    question = ""
    key_facts = []
    keywords = []
    difficulty = "medium"

    for line in lines:
        line = line.strip()
        if line.startswith("PYTANIE:"):
            question = line[len("PYTANIE:"):].strip()
        elif line.startswith("FAKT:"):
            f = line[len("FAKT:"):].strip()
            if f:
                key_facts.append(f)
        elif line.startswith("KLUCZOWE:"):
            k = line[len("KLUCZOWE:"):].strip()
            if k:
                keywords.append(k)
        elif line.startswith("TRUDNOŚĆ:"):
            d = line[len("TRUDNOŚĆ:"):].strip().lower()
            if "łatw" in d:
                difficulty = "easy"
            elif "trudn" in d:
                difficulty = "hard"

    if not question or len(question) < 20:
        return None

    # Infer category from publisher
    publisher = chunk.get("publisher", "WDU")
    if publisher in SAOS_PUBLISHERS:
        category = "judgment"
    elif publisher == "KIS":
        category = "tax"
    else:
        category = "legislation"

    return {
        "id": question_id,
        "category": category,
        "question": question,
        "expected_act_keywords": keywords,
        "key_facts": key_facts,
        "source_act_id": chunk.get("act_id", ""),
        "source_title": chunk.get("title", ""),
        "source_year": str(chunk.get("year", "")),
        "difficulty": difficulty,
    }


def generate_question(chunk: dict, client, model: str, question_id: int) -> dict | None:
    """Generate one eval question from a single chunk."""
    text = chunk.get("text", "")[:1500]
    title = chunk.get("title", "")
    prompt = f"Tytuł dokumentu: {title}\n\nFragment:\n{text}"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_QUESTION_GEN},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=400,
        )
        return _parse_question_response(
            resp.choices[0].message.content, chunk, question_id
        )
    except Exception as exc:
        log.warning("Question generation failed: %s", exc)
        return None


def select_representative_chunks(
    all_chunks: list[dict],
    n_per_category: dict[str, int],
) -> list[dict]:
    """
    Select diverse chunks for question generation:
    - Prioritize chunks from different acts (not all from same ustawa)
    - Prefer substantive chunks (thesis/ruling sections for SAOS)
    - Filter out very short or boilerplate chunks
    """
    result: list[dict] = []

    for category, n in n_per_category.items():
        predicate = CATEGORY_MAP.get(category, lambda _: True)
        candidates = [
            c for c in all_chunks
            if predicate(c)
            and len(c.get("text", "")) >= 300  # minimum substance
            and c.get("chunk_index", 0) > 0    # skip first chunk (often header)
        ]

        if not candidates:
            log.warning("No chunks found for category '%s'", category)
            continue

        # Sample from diverse acts (at most 2 chunks per act)
        seen_acts: dict[str, int] = {}
        diverse: list[dict] = []
        random.shuffle(candidates)
        for chunk in candidates:
            act_id = chunk.get("act_id", "")
            if seen_acts.get(act_id, 0) < 2:
                diverse.append(chunk)
                seen_acts[act_id] = seen_acts.get(act_id, 0) + 1
            if len(diverse) >= n * 3:  # oversample, then trim after generation
                break

        selected = diverse[:n]
        log.info("Category '%s': selected %d chunks from %d acts", category, len(selected), len(seen_acts))
        result.extend(selected)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Polish legal QA evaluation benchmark from chunks."
    )
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/eval_questions.jsonl"))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--n-questions", type=int, default=200,
                        help="Total number of questions to generate")
    parser.add_argument("--categories", default="legislation:120,judgment:60,tax:20",
                        help="Category:count pairs, e.g. 'legislation:100,judgment:60,tax:40'")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true", help="Show selection stats without LLM calls")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        log.error("OPENAI_API_KEY not set")
        sys.exit(1)

    random.seed(args.seed)

    if not args.input.exists():
        log.error("Input not found: %s", args.input)
        sys.exit(1)

    log.info("Loading chunks …")
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

    # Parse category spec
    n_per_category: dict[str, int] = {}
    for spec in args.categories.split(","):
        parts = spec.strip().split(":")
        if len(parts) == 2:
            cat, n = parts[0].strip(), int(parts[1].strip())
            n_per_category[cat] = n
        else:
            log.warning("Ignoring invalid category spec: %s", spec)

    log.info("Target: %s", n_per_category)

    selected = select_representative_chunks(all_chunks, n_per_category)
    log.info("Selected %d chunks for question generation", len(selected))

    if args.dry_run:
        log.info("DRY RUN — not calling LLM. Would generate %d questions from %d chunks.",
                 len(selected), len(selected))
        by_cat: dict[str, int] = {}
        for chunk in selected:
            pub = chunk.get("publisher", "WDU")
            cat = "judgment" if pub in SAOS_PUBLISHERS else ("tax" if pub == "KIS" else "legislation")
            by_cat[cat] = by_cat.get(cat, 0) + 1
        log.info("By category: %s", by_cat)
        return

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    questions: list[dict] = []
    question_id = 1
    total = len(selected)

    for i, chunk in enumerate(selected, 1):
        log.info("[%d/%d] Generating question for %s …", i, total, chunk.get("title", "")[:60])
        q = generate_question(chunk, client, args.model, question_id)
        if q:
            questions.append(q)
            question_id += 1
        if i % 10 == 0:
            time.sleep(0.5)  # gentle rate limiting

    # Write output (append to existing if file exists, for resumability)
    existing: list[dict] = []
    if args.output.exists():
        with args.output.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        log.info("Appending to existing %d questions", len(existing))
        max_id = max((q["id"] for q in existing), default=0)
        for q in questions:
            q["id"] += max_id

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for q in existing + questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    total_written = len(existing) + len(questions)
    log.info(
        "Done. Generated %d new questions. Total in benchmark: %d → %s",
        len(questions), total_written, args.output,
    )

    by_cat: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    for q in questions:
        by_cat[q["category"]] = by_cat.get(q["category"], 0) + 1
        by_diff[q["difficulty"]] = by_diff.get(q["difficulty"], 0) + 1
    log.info("By category: %s", by_cat)
    log.info("By difficulty: %s", by_diff)


if __name__ == "__main__":
    main()
