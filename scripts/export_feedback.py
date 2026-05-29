"""
export_feedback.py — Export user feedback for fine-tuning.

Reads the Prisma SQLite database, joins Feedback ↔ QueryLog, and writes
JSONL fine-tuning data. Positive feedback (rating=+1) becomes training examples;
negative feedback (rating=-1) is optionally included with quality=bad tag.

Output format: OpenAI / Bielik chat JSONL (messages array + metadata)

Usage:
    python scripts/export_feedback.py --output data/dataset/feedback/train.jsonl
    python scripts/export_feedback.py --positive-only
    python scripts/export_feedback.py --min-rating 1 --output data/dataset/feedback/positive.jsonl
    python scripts/export_feedback.py --stats
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DEFAULT_DB = Path("frontend/prisma/prod.db")
SYSTEM_PROMPT = (
    "Jesteś polskim asystentem prawnym. "
    "Odpowiadaj precyzyjnie i rzetelnie na podstawie aktów prawnych i orzecznictwa."
)


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        log.error("Database not found: %s", db_path)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_feedback(
    conn: sqlite3.Connection,
    min_rating: int | None = None,
    positive_only: bool = False,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    conditions = []
    params: list = []

    if positive_only:
        conditions.append("f.rating = 1")
    elif min_rating is not None:
        conditions.append("f.rating >= ?")
        params.append(min_rating)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    lim = f"LIMIT {limit}" if limit else ""

    sql = f"""
        SELECT
            f.id          AS feedback_id,
            f.rating,
            f.comment,
            f.createdAt   AS feedback_at,
            q.id          AS query_log_id,
            q.question,
            q.answer,
            q.sources,
            q.modelUsed   AS model_used,
            q.createdAt   AS query_at
        FROM Feedback f
        JOIN QueryLog q ON f.queryLogId = q.id
        {where}
        ORDER BY f.createdAt DESC
        {lim}
    """
    return conn.execute(sql, params).fetchall()


def print_stats(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM Feedback").fetchone()[0]
    pos   = conn.execute("SELECT COUNT(*) FROM Feedback WHERE rating = 1").fetchone()[0]
    neg   = conn.execute("SELECT COUNT(*) FROM Feedback WHERE rating = -1").fetchone()[0]
    print(f"\nFeedback statistics:")
    print(f"  Total:    {total}")
    print(f"  Positive: {pos} ({pos/total*100:.1f}%)" if total else "  Positive: 0")
    print(f"  Negative: {neg} ({neg/total*100:.1f}%)" if total else "  Negative: 0")
    print()


def row_to_finetune(row: sqlite3.Row) -> dict:
    try:
        sources = json.loads(row["sources"])
    except (json.JSONDecodeError, TypeError):
        sources = []

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": row["question"]},
            {"role": "assistant", "content": row["answer"]},
        ],
        "metadata": {
            "rating":      row["rating"],
            "quality":     "good" if row["rating"] == 1 else "bad",
            "model":       row["model_used"],
            "n_sources":   len(sources),
            "feedback_id": row["feedback_id"],
            "created_at":  row["feedback_at"],
            "comment":     row["comment"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export user feedback as fine-tuning JSONL.")
    parser.add_argument(
        "--output", type=Path, default=Path("data/dataset/feedback/train.jsonl"),
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB,
        help=f"SQLite database path (default: {DEFAULT_DB})",
    )
    parser.add_argument("--positive-only", action="store_true", help="Export only thumbs-up examples")
    parser.add_argument("--min-rating", type=int, default=None, choices=[-1, 1], help="Filter by minimum rating")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to export")
    parser.add_argument("--stats", action="store_true", help="Print statistics and exit")
    args = parser.parse_args()

    conn = connect(args.db)

    if args.stats:
        print_stats(conn)
        return

    rows = fetch_feedback(
        conn,
        min_rating=args.min_rating,
        positive_only=args.positive_only,
        limit=args.limit,
    )
    log.info("Fetched %d feedback records", len(rows))

    if not rows:
        log.warning("No feedback records found (have users rated any answers yet?)")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("w", encoding="utf-8") as fout:
        for row in rows:
            entry = row_to_finetune(row)
            fout.write(json.dumps(entry, ensure_ascii=False) + "\n")
            written += 1

    pos = sum(1 for r in rows if r["rating"] == 1)
    neg = written - pos
    log.info("Wrote %d records to %s (positive=%d, negative=%d)", written, args.output, pos, neg)
    print(f"\nFine-tuning data ready: {args.output}")
    print(f"  Positive examples (thumbs up):  {pos}")
    print(f"  Negative examples (thumbs down): {neg}")
    print(f"\nNext step — merge with synthetic data and train:")
    print(f"  python training/train.py --data {args.output}")


if __name__ == "__main__":
    main()
