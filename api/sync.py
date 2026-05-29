"""
sync.py — Automatic weekly SAOS sync scheduler.

Runs inside the API process using APScheduler.
Every week (default: Sunday 03:00) fetches new SAOS judgments,
preprocesses them, and ingests into Qdrant without rebuilding the collection.

Environment variables:
    SYNC_ENABLED        true | false (default: true)
    SYNC_CRON           cron expression, default "0 3 * * 0" (Sun 3am)
    SYNC_SINCE_DAYS     how many days back to fetch (default: 8, overlapping for safety)
    SYNC_SAOS_OUTPUT    where to write new SAOS JSONL (default: /app/data/raw)
    SYNC_PROCESSED_DIR  where preprocessed chunks go (default: /app/data/processed)
    QDRANT_PATH         inherited from main (http://qdrant:6333 in Docker)
    EMBEDDING_MODEL     inherited from main
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SYNC_ENABLED      = os.getenv("SYNC_ENABLED", "true").lower() not in ("false", "0", "no")
SYNC_CRON         = os.getenv("SYNC_CRON", "0 3 * * 0")           # Sunday 03:00
SYNC_SINCE_DAYS   = int(os.getenv("SYNC_SINCE_DAYS", "8"))
SYNC_SAOS_OUTPUT  = Path(os.getenv("SYNC_SAOS_OUTPUT", "/app/data/raw"))
SYNC_PROCESSED    = Path(os.getenv("SYNC_PROCESSED_DIR", "/app/data/processed"))
QDRANT_PATH       = os.getenv("QDRANT_PATH", "http://qdrant:6333")
EMBEDDING_MODEL   = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "lexcorpus")

# ── Shared state (read from /sync/status endpoint) ────────────────────────────

_status: dict[str, Any] = {
    "last_run_start":  None,
    "last_run_end":    None,
    "last_run_ok":     None,
    "last_run_log":    [],
    "next_run":        None,
    "running":         False,
    "runs_total":      0,
    "runs_failed":     0,
}
_lock = threading.Lock()

# ── Sync logic ────────────────────────────────────────────────────────────────

def _run_cmd(args: list[str], label: str, lines: list[str]) -> bool:
    """Run a subprocess, stream output to log and lines list. Returns True on success."""
    log.info("[sync] %s: %s", label, " ".join(args))
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout
        for line in proc.stdout:
            line = line.rstrip()
            log.info("[sync][%s] %s", label, line)
            lines.append(f"[{label}] {line}")
        proc.wait()
        if proc.returncode != 0:
            lines.append(f"[{label}] EXIT {proc.returncode}")
            return False
        return True
    except Exception as exc:
        lines.append(f"[{label}] ERROR: {exc}")
        log.error("[sync] %s failed: %s", label, exc)
        return False


def run_sync() -> None:
    """Full sync pipeline: fetch → preprocess → ingest (append mode)."""
    with _lock:
        if _status["running"]:
            log.warning("[sync] Already running — skipping")
            return
        _status["running"] = True
        _status["last_run_start"] = datetime.now(timezone.utc).isoformat()
        _status["last_run_log"] = []
        _status["runs_total"] += 1

    lines: list[str] = _status["last_run_log"]
    ok = False
    since_date = (datetime.now(timezone.utc) - timedelta(days=SYNC_SINCE_DAYS)).strftime("%Y-%m-%d")
    python = sys.executable

    try:
        lines.append(f"Sync start — since {since_date}")
        SYNC_SAOS_OUTPUT.mkdir(parents=True, exist_ok=True)
        SYNC_PROCESSED.mkdir(parents=True, exist_ok=True)

        # Step 1: fetch new SAOS judgments
        ok = _run_cmd(
            [python, "scripts/fetch_saos.py",
             "--since-date", since_date,
             "--output", str(SYNC_SAOS_OUTPUT)],
            "fetch-saos",
            lines,
        )
        if not ok:
            lines.append("Fetch failed — aborting sync")
            return

        # Step 2: find the newly written SAOS file and preprocess it
        new_files = sorted(SYNC_SAOS_OUTPUT.glob("saos_sync_*.jsonl"))
        if not new_files:
            # Fallback: re-preprocess all saos_*.jsonl
            new_files = sorted(SYNC_SAOS_OUTPUT.glob("saos_*.jsonl"))

        if not new_files:
            lines.append("No SAOS files found after fetch — nothing to ingest")
            ok = True
            return

        ok = _run_cmd(
            [python, "scripts/preprocess.py",
             "--input", str(new_files[-1]),
             "--output", str(SYNC_PROCESSED)],
            "preprocess",
            lines,
        )
        if not ok:
            lines.append("Preprocess failed — aborting sync")
            return

        # Step 3: ingest new chunks (append, no --recreate)
        chunk_file = SYNC_PROCESSED / f"chunks_{new_files[-1].stem}.jsonl"
        if not chunk_file.exists():
            # try generic merged file
            chunk_file = SYNC_PROCESSED / "chunks.jsonl"

        ok = _run_cmd(
            [python, "rag/ingest.py",
             "--input", str(chunk_file),
             "--qdrant", QDRANT_PATH,
             "--collection", QDRANT_COLLECTION,
             "--model", EMBEDDING_MODEL],
            "ingest",
            lines,
        )

        if ok:
            # Update sentinel mtime so /stats shows correct last_ingest
            sentinel = Path(QDRANT_PATH.split("://")[-1].split(":")[0]
                            if QDRANT_PATH.startswith("http") else QDRANT_PATH) / ".ingested"
            try:
                sentinel.parent.mkdir(parents=True, exist_ok=True)
                sentinel.touch()
            except Exception:
                pass
            lines.append("Sync complete ✓")

            # Step 4: detect changes and match with user query history
            db_path = os.getenv("DATABASE_PATH", "frontend/prisma/dev.db")
            if chunk_file.exists():
                _run_cmd(
                    [python, "scripts/detect_changes.py",
                     "--new-chunks", str(chunk_file),
                     "--db", db_path,
                     "--threshold", "0.72"],
                    "detect-changes",
                    lines,
                )
        else:
            lines.append("Ingest failed")

    except Exception as exc:
        lines.append(f"Unexpected error: {exc}")
        log.exception("[sync] Unexpected error")
        ok = False
    finally:
        with _lock:
            _status["running"] = False
            _status["last_run_end"] = datetime.now(timezone.utc).isoformat()
            _status["last_run_ok"] = ok
            if not ok:
                _status["runs_failed"] += 1


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Start the APScheduler background scheduler. Called once at API startup."""
    if not SYNC_ENABLED:
        log.info("[sync] SYNC_ENABLED=false — scheduler disabled")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("[sync] apscheduler not installed — auto-sync disabled")
        return

    parts = SYNC_CRON.split()
    if len(parts) != 5:
        log.error("[sync] Invalid SYNC_CRON '%s' — expected 5 fields", SYNC_CRON)
        return

    minute, hour, day, month, day_of_week = parts
    trigger = CronTrigger(
        minute=minute, hour=hour,
        day=day, month=month,
        day_of_week=day_of_week,
        timezone="Europe/Warsaw",
    )

    scheduler = BackgroundScheduler(timezone="Europe/Warsaw")
    job = scheduler.add_job(run_sync, trigger, id="saos_sync", replace_existing=True)
    scheduler.start()

    next_run = job.next_run_time
    with _lock:
        _status["next_run"] = next_run.isoformat() if next_run else None

    log.info(
        "[sync] Scheduler started — cron='%s', next run: %s",
        SYNC_CRON,
        next_run.strftime("%Y-%m-%d %H:%M %Z") if next_run else "unknown",
    )


def get_status() -> dict:
    with _lock:
        return dict(_status)


def trigger_sync() -> dict:
    """Trigger sync immediately in a background thread."""
    if _status["running"]:
        return {"ok": False, "detail": "Sync already running"}
    t = threading.Thread(target=run_sync, daemon=True, name="saos-sync-manual")
    t.start()
    return {"ok": True, "detail": "Sync triggered"}
