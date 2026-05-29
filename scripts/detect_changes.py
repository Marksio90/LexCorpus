"""
detect_changes.py — Legal Diff: wykrywa nowe/zmienione przepisy po sync i
dopasowuje je do historii zapytań użytkowników (cosine similarity).

Uruchamiany automatycznie po każdym udanym sync przez api/sync.py.
Zapisuje wyniki do SQLite (LegalChange + LegalAlert).

Usage:
    python scripts/detect_changes.py \
        --new-chunks data/processed/chunks_saos_sync_2025.jsonl \
        --db frontend/prisma/prod.db \
        --qdrant http://qdrant:6333 \
        --threshold 0.72
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

DEFAULT_DB   = os.getenv("DATABASE_PATH", "frontend/prisma/dev.db")
DEFAULT_QDRANT = os.getenv("QDRANT_PATH", "data/qdrant")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

SUMMARY_PROMPT = """Poniżej fragment nowego/zmienionego przepisu prawnego lub orzeczenia sądowego.
Napisz 1-2 zdania po polsku (max 200 znaków) wyjaśniające co konkretnie się zmieniło lub co jest istotne.
Bądź precyzyjny i konkretny.

Tytuł: {title}
Fragment: {text}

Podsumowanie:"""


def load_new_chunks(path: Path) -> list[dict]:
    chunks = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    log.info("Załadowano %d nowych chunków z %s", len(chunks), path)
    return chunks


def get_recent_questions(db_path: str, limit: int = 2000) -> list[dict]:
    """Pobiera ostatnie pytania wszystkich userów z QueryLog."""
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            """SELECT id, userId, question
               FROM QueryLog
               ORDER BY createdAt DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "userId": r[1], "question": r[2]} for r in rows]
    except Exception as e:
        log.warning("Błąd odczytu QueryLog: %s", e)
        return []


def already_processed(db_path: str, act_id: str, chunk_index: int) -> bool:
    """Sprawdza czy ten chunk już był przetworzony jako zmiana."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT 1 FROM LegalChange WHERE actId=? AND json_extract(chunkText,'$') IS NOT NULL LIMIT 1",
            (act_id,),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def save_change(db_path: str, chunk: dict, summary: str) -> str | None:
    """Zapisuje LegalChange do SQLite, zwraca id."""
    try:
        conn = sqlite3.connect(db_path)
        cid = f"chg_{chunk.get('act_id','')}_{chunk.get('chunk_index',0)}_{int(datetime.now().timestamp())}"
        conn.execute(
            """INSERT OR IGNORE INTO LegalChange
               (id, actId, title, sourceType, year, summary, chunkText, url, detectedAt)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                cid,
                chunk.get("act_id", ""),
                chunk.get("title", ""),
                chunk.get("source_type", "unknown"),
                chunk.get("year"),
                summary,
                chunk.get("text", "")[:1000],
                chunk.get("url"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return cid
    except Exception as e:
        log.warning("Błąd zapisu LegalChange: %s", e)
        return None


def save_alert(db_path: str, user_id: str, change_id: str, similarity: float, question: str) -> None:
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT OR IGNORE INTO LegalAlert
               (id, userId, changeId, similarity, question, createdAt)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                f"alr_{user_id[:8]}_{change_id[-8:]}",
                user_id,
                change_id,
                round(similarity, 4),
                question,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("Błąd zapisu LegalAlert: %s", e)


def generate_summary(chunk: dict, openai_key: str | None) -> str:
    """Generuje 1-2 zdaniowe podsumowanie zmiany przez GPT-4o-mini."""
    if not openai_key:
        # Fallback: pierwsze 200 znaków tekstu
        return chunk.get("text", "")[:200].strip()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        prompt = SUMMARY_PROMPT.format(
            title=chunk.get("title", ""),
            text=chunk.get("text", "")[:600],
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning("Błąd generowania podsumowania: %s", e)
        return chunk.get("text", "")[:200].strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-chunks",  type=Path, required=True)
    parser.add_argument("--db",          default=DEFAULT_DB)
    parser.add_argument("--qdrant",      default=DEFAULT_QDRANT)
    parser.add_argument("--threshold",   type=float, default=0.72,
                        help="Min cosine similarity do wygenerowania alertu")
    parser.add_argument("--max-chunks",  type=int,   default=500,
                        help="Max nowych chunków do przetworzenia per run")
    args = parser.parse_args()

    if not args.new_chunks.exists():
        log.error("Plik chunków nie istnieje: %s", args.new_chunks)
        sys.exit(1)

    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        log.error("Brakuje sentence-transformers lub numpy")
        sys.exit(1)

    log.info("Ładowanie modelu embeddingow: %s", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)

    new_chunks = load_new_chunks(args.new_chunks)[: args.max_chunks]
    if not new_chunks:
        log.info("Brak nowych chunków — koniec")
        return

    questions = get_recent_questions(args.db)
    if not questions:
        log.info("Brak historii pytań — pomijam matching")

    openai_key = os.getenv("OPENAI_API_KEY")

    # Embed pytania userów (batch)
    q_texts   = [q["question"] for q in questions]
    q_vectors = model.encode(q_texts, show_progress_bar=False, normalize_embeddings=True) if q_texts else []

    alerts_created = 0
    changes_created = 0

    for chunk in new_chunks:
        act_id      = chunk.get("act_id", "")
        chunk_index = chunk.get("chunk_index", 0)
        text        = chunk.get("text", "").strip()
        if not text or not act_id:
            continue

        # Embed nowy chunk
        chunk_vec = model.encode([text], normalize_embeddings=True)[0]

        # Generuj podsumowanie
        summary = generate_summary(chunk, openai_key)

        # Zapisz zmianę
        change_id = save_change(args.db, chunk, summary)
        if not change_id:
            continue
        changes_created += 1

        if not q_texts:
            continue

        # Cosine similarity (wektory znormalizowane → dot product)
        sims = np.dot(q_vectors, chunk_vec)  # shape: (N,)

        # Grupuj po userId — weź najwyższy score per user
        best_per_user: dict[str, tuple[float, str]] = {}
        for i, q in enumerate(questions):
            uid  = q["userId"]
            sim  = float(sims[i])
            if sim < args.threshold:
                continue
            if uid not in best_per_user or sim > best_per_user[uid][0]:
                best_per_user[uid] = (sim, q["question"])

        for uid, (sim, question) in best_per_user.items():
            save_alert(args.db, uid, change_id, sim, question)
            alerts_created += 1

    log.info("Gotowe — %d zmian, %d alertów (próg=%.2f)", changes_created, alerts_created, args.threshold)

    # Registry subscriptions — notify users watching changed acts directly
    registry_notified = notify_registry_subscribers(args.db, new_chunks)
    if registry_notified:
        log.info("Powiadomiono %d subskrybentów rejestru", registry_notified)


# ── Registry subscription notifications ───────────────────────────────────────

def get_registry_subscribers(db_path: str, act_id: str) -> list[dict]:
    """Returns users subscribed to a specific actId with their email."""
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            """SELECT rs.userId, u.email, rs.title, rs.url
               FROM RegistrySubscription rs
               JOIN User u ON u.id = rs.userId
               WHERE rs.actId = ? AND u.email IS NOT NULL""",
            (act_id,),
        ).fetchall()
        conn.close()
        return [{"userId": r[0], "email": r[1], "title": r[2], "url": r[3]} for r in rows]
    except Exception as e:
        log.warning("Błąd pobierania subskrybentów rejestru: %s", e)
        return []


def notify_registry_subscribers(db_path: str, new_chunks: list[dict]) -> int:
    """Send immediate email to users who subscribed to acts present in new_chunks."""
    smtp_host     = os.getenv("EMAIL_SERVER_HOST", "")
    smtp_port     = int(os.getenv("EMAIL_SERVER_PORT", "587"))
    smtp_user     = os.getenv("EMAIL_SERVER_USER", "")
    smtp_pass     = os.getenv("EMAIL_SERVER_PASSWORD", "")
    email_from    = os.getenv("EMAIL_FROM", "LexCorpus <noreply@lexcorpus.app>")
    base_url      = os.getenv("NEXTAUTH_URL", "http://localhost:3000")

    if not smtp_host or not smtp_user:
        log.info("SMTP nie skonfigurowany — pomijam powiadomienia rejestru")
        return 0

    # Deduplicate: one email per (userId, actId) per run
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    # Group chunks by act_id
    chunks_by_act: dict[str, list[dict]] = {}
    for chunk in new_chunks:
        aid = chunk.get("act_id", "")
        if aid:
            chunks_by_act.setdefault(aid, []).append(chunk)

    notified: set[tuple[str, str]] = set()  # (userId, actId)
    count = 0

    for act_id, chunks in chunks_by_act.items():
        subscribers = get_registry_subscribers(db_path, act_id)
        if not subscribers:
            continue

        chunk = chunks[0]  # representative chunk
        act_title = chunk.get("title", act_id)
        act_url   = chunk.get("url", "")
        summary   = chunk.get("summary", chunk.get("text", "")[:200])

        for sub in subscribers:
            key = (sub["userId"], act_id)
            if key in notified:
                continue
            notified.add(key)

            try:
                html = _build_registry_email(
                    sub["email"], act_title, act_url or sub.get("url") or "",
                    summary, base_url,
                )
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"⚖️ LexCorpus: zmiana w „{act_title[:60]}"
                msg["From"]    = email_from
                msg["To"]      = sub["email"]
                msg.attach(MIMEText(html, "html", "utf-8"))

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    if smtp_user:
                        server.login(smtp_user, smtp_pass)
                    server.sendmail(email_from, [sub["email"]], msg.as_string())

                count += 1
                log.info("Powiadomiono %s o zmianach w %s", sub["email"], act_id)
            except Exception as e:
                log.warning("Błąd wysyłania do %s: %s", sub["email"], e)

    return count


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _build_registry_email(email: str, act_title: str, act_url: str, summary: str, base_url: str) -> str:
    unsub_url  = f"{base_url}/registry"
    safe_title = _esc(act_title)
    safe_sum   = _esc(summary)
    safe_url   = _esc(act_url)
    doc_link   = f'<a href="{safe_url}" style="color:#2563eb">Otwórz akt ↗</a>' if act_url else ""
    return f"""<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 16px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">
        <tr>
          <td style="background:linear-gradient(135deg,#1d4ed8,#2563eb);padding:28px 40px">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700"><span style="opacity:.8">Lex</span>Corpus</h1>
            <p style="margin:4px 0 0;color:#bfdbfe;font-size:13px">Powiadomienie o zmianie w obserwowanym akcie</p>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 40px">
            <p style="margin:0 0 6px;font-size:13px;color:#64748b">Obserwowany akt:</p>
            <h2 style="margin:0 0 16px;font-size:17px;color:#0f172a;font-weight:700">{safe_title}</h2>
            <p style="margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6">{safe_sum}</p>
            <div style="display:flex;gap:16px;font-size:13px">
              {doc_link}
              <a href="{base_url}/alerts" style="color:#2563eb">Zobacz alerty →</a>
            </div>
          </td>
        </tr>
        <tr>
          <td style="background:#f8fafc;padding:16px 40px;border-top:1px solid #e2e8f0">
            <p style="margin:0;color:#94a3b8;font-size:11px;text-align:center">
              Obserwujesz ten akt w LexCorpus.
              <a href="{unsub_url}" style="color:#94a3b8">Zarządzaj subskrypcjami</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


if __name__ == "__main__":
    main()
