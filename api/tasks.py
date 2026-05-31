"""
tasks.py — Celery worker do asynchronicznego przetwarzania prywatnych dokumentów.

Broker i backend: Redis (ten sam co rate limiter).
Task: process_private_document — parsuje PDF/DOCX/TXT, embedduje, ładuje do Qdrant,
      aktualizuje status w PostgreSQL.

Uruchamianie workera:
    celery -A api.tasks worker --loglevel=info --concurrency=2
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import re

from celery import Celery

log = logging.getLogger(__name__)


def _extract_text(path: Path, mime_type: str) -> str:
    """Extract plain text from PDF, DOCX, or TXT files."""
    if mime_type == "text/plain" or path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            pass
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        except ImportError:
            raise RuntimeError("Zainstaluj pypdf lub pdfplumber: pip install pypdf")
    if path.suffix.lower() in (".docx", ".doc"):
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise RuntimeError("Zainstaluj python-docx: pip install python-docx")
    raise RuntimeError(f"Nieobsługiwany format: {path.suffix}")


_CHUNK_SIZE = 512
_CHUNK_OVERLAP = 64


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping sentence-based chunks."""
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sent in sentences:
        words = len(sent.split())
        if current_len + words > _CHUNK_SIZE and current:
            chunks.append(" ".join(current))
            overlap_words = " ".join(current).split()[-_CHUNK_OVERLAP:]
            current = [" ".join(overlap_words)]
            current_len = len(overlap_words)
        current.append(sent)
        current_len += words
    if current:
        chunks.append(" ".join(current))
    return [c.strip() for c in chunks if c.strip()]

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "")
QDRANT_URL = os.getenv("QDRANT_PATH", "http://qdrant:6333")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

celery_app = Celery(
    "lexcorpus",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,          # potwierdź dopiero po wykonaniu (retry przy crash workera)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # jeden task na raz — embedding jest ciężkie
    task_track_started=True,
)


def _update_status_pg(doc_id: str, status: str, chunk_count: int = 0, error: str | None = None) -> None:
    """Aktualizuje status PrivateDocument w PostgreSQL (synchronicznie przez psycopg2)."""
    if not DATABASE_URL:
        log.warning("DATABASE_URL nie ustawiony — pomijam aktualizację statusu")
        return
    try:
        import psycopg2
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE "PrivateDocument"
                       SET status=%s, "chunkCount"=%s, "errorMsg"=%s, "processedAt"=NOW()
                       WHERE id=%s""",
                    (status, chunk_count, error, doc_id),
                )
            conn.commit()
    except Exception as exc:
        log.warning("Błąd aktualizacji statusu doc %s: %s", doc_id, exc)


@celery_app.task(
    bind=True,
    name="lexcorpus.process_private_document",
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=300,   # 5 min — PDF może być duży
    time_limit=360,
)
def process_private_document(
    self,
    doc_id: str,
    user_id: str,
    file_path: str,
    mime_type: str,
) -> dict:
    """
    Przetwarza prywatny dokument użytkownika:
    1. Ekstrakcja tekstu (PDF/DOCX/TXT)
    2. Chunking
    3. Embedding (SentenceTransformer)
    4. Upsert do Qdrant (kolekcja per-user)
    5. Aktualizacja statusu w PostgreSQL
    """
    log.info("START process_private_document doc_id=%s user_id=%s", doc_id, user_id)
    path = Path(file_path)

    if not path.exists():
        err = f"Plik nie istnieje: {file_path}"
        _update_status_pg(doc_id, "error", error=err)
        raise FileNotFoundError(err)

    # ── 1. Ekstrakcja tekstu ──────────────────────────────────────────────────
    try:
        text = _extract_text(path, mime_type)
    except Exception as exc:
        err = f"Błąd ekstrakcji tekstu: {exc}"
        log.error(err)
        _update_status_pg(doc_id, "error", error=err)
        raise self.retry(exc=exc)

    if not text.strip():
        err = "Dokument jest pusty lub nie można odczytać tekstu."
        _update_status_pg(doc_id, "error", error=err)
        return {"status": "error", "error": err}

    # ── 2. Chunking ───────────────────────────────────────────────────────────
    chunks = _chunk_text(text)
    log.info("Podzielono na %d chunków", len(chunks))

    # ── 3. Embedding ──────────────────────────────────────────────────────────
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBEDDING_MODEL)
        dim = model.get_sentence_embedding_dimension()
        vectors = model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)
    except Exception as exc:
        err = f"Błąd embeddingu: {exc}"
        log.error(err)
        _update_status_pg(doc_id, "error", error=err)
        raise self.retry(exc=exc)

    # ── 4. Upsert do Qdrant ───────────────────────────────────────────────────
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels

        collection = f"lexcorpus_private_{user_id}"
        client = (
            QdrantClient(url=QDRANT_URL, timeout=60)
            if QDRANT_URL.startswith("http")
            else QdrantClient(path=QDRANT_URL)
        )

        try:
            client.delete_collection(collection)
        except Exception:
            pass
        client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
        )

        batch_size = 100
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start: start + batch_size]
            batch_vectors = vectors[start: start + batch_size]
            points = [
                qmodels.PointStruct(
                    id=start + i,
                    vector=batch_vectors[i].tolist(),
                    payload={"chunk_index": start + i, "text": batch_chunks[i],
                             "doc_id": doc_id, "user_id": user_id},
                )
                for i in range(len(batch_chunks))
            ]
            client.upsert(collection_name=collection, points=points, wait=True)

    except Exception as exc:
        err = f"Błąd Qdrant: {exc}"
        log.error(err)
        _update_status_pg(doc_id, "error", error=err)
        raise self.retry(exc=exc)

    # ── 5. Aktualizacja statusu ───────────────────────────────────────────────
    _update_status_pg(doc_id, "ready", chunk_count=len(chunks))
    log.info("DONE doc_id=%s — %d chunków w kolekcji %s", doc_id, len(chunks), collection)

    # Usuń tymczasowy plik po przetworzeniu
    try:
        path.unlink()
    except Exception:
        pass

    return {"status": "ready", "chunk_count": len(chunks)}
