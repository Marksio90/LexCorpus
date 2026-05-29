"""
ingest_private.py — Przetwarza prywatny dokument użytkownika i ładuje do
osobnej kolekcji Qdrant: lexcorpus_private_{userId}.

Obsługuje: PDF, TXT, DOCX (przez python-docx jeśli dostępne).

Usage:
    python scripts/ingest_private.py \
        --file /tmp/upload_abc.pdf \
        --user-id cuid123 \
        --doc-id docid456 \
        --db frontend/prisma/dev.db \
        --qdrant http://qdrant:6333
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
QDRANT_PATH     = os.getenv("QDRANT_PATH", "data/qdrant")
CHUNK_SIZE      = 512    # tokens approx — znaków / 4
CHUNK_OVERLAP   = 64


def extract_text(path: Path, mime: str) -> str:
    """Wyciąga tekst z pliku."""
    if mime == "text/plain" or path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            log.warning("pypdf nie jest zainstalowane — próba pdfplumber")
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


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Prosta chunking na zdaniach z overlapem."""
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
    chunks, current, current_len = [], [], 0

    for sent in sentences:
        words = len(sent.split())
        if current_len + words > chunk_size and current:
            chunks.append(" ".join(current))
            # Overlap: zostaw ostatnie N słów
            overlap_words = " ".join(current).split()[-overlap:]
            current = [" ".join(overlap_words)]
            current_len = len(overlap_words)
        current.append(sent)
        current_len += words

    if current:
        chunks.append(" ".join(current))

    return [c.strip() for c in chunks if c.strip()]


def update_status(db: str, doc_id: str, status: str, chunk_count: int = 0, error: str | None = None) -> None:
    try:
        conn = sqlite3.connect(db)
        conn.execute(
            """UPDATE PrivateDocument SET status=?, chunkCount=?, errorMsg=?,
               processedAt=datetime('now') WHERE id=?""",
            (status, chunk_count, error, doc_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("Błąd aktualizacji statusu: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file",    required=True, type=Path)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--doc-id",  required=True)
    parser.add_argument("--mime",    default="application/octet-stream")
    parser.add_argument("--db",      default=os.getenv("DATABASE_PATH", "frontend/prisma/dev.db"))
    parser.add_argument("--qdrant",  default=QDRANT_PATH)
    args = parser.parse_args()

    collection = f"lexcorpus_private_{args.user_id}"

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        update_status(args.db, args.doc_id, "error", error=str(e))
        sys.exit(1)

    try:
        text = extract_text(args.file, args.mime)
    except Exception as e:
        log.error("Błąd ekstrakcji tekstu: %s", e)
        update_status(args.db, args.doc_id, "error", error=str(e))
        sys.exit(1)

    if not text.strip():
        update_status(args.db, args.doc_id, "error", error="Dokument jest pusty lub nie można odczytać tekstu.")
        sys.exit(1)

    chunks = chunk_text(text)
    log.info("Podzielono na %d chunków", len(chunks))

    model = SentenceTransformer(EMBEDDING_MODEL)
    dim   = model.get_sentence_embedding_dimension()

    if args.qdrant.startswith("http"):
        client = QdrantClient(url=args.qdrant, timeout=60)
    else:
        client = QdrantClient(path=args.qdrant)

    # Utwórz lub zresetuj kolekcję dla tego użytkownika
    try:
        client.delete_collection(collection)
    except Exception:
        pass
    client.create_collection(
        collection_name=collection,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )

    # Embed i zaindeksuj
    vectors = model.encode(chunks, show_progress_bar=True, normalize_embeddings=True)
    points  = [
        qmodels.PointStruct(
            id=i,
            vector=vectors[i].tolist(),
            payload={
                "chunk_index": i,
                "text":        chunks[i],
                "doc_id":      args.doc_id,
                "user_id":     args.user_id,
            },
        )
        for i in range(len(chunks))
    ]

    batch_size = 100
    for start in range(0, len(points), batch_size):
        client.upsert(collection_name=collection, points=points[start: start + batch_size])

    update_status(args.db, args.doc_id, "ready", chunk_count=len(chunks))
    log.info("Zaindeksowano %d chunków w kolekcji %s", len(chunks), collection)


if __name__ == "__main__":
    main()
