"""
ingest_sample.py — CI helper: ingest a small synthetic dataset into Qdrant for eval tests.

Generates fake legal chunk records and embeds them so run_eval.py can test retrieval
without needing the full 636k-document dataset.

Usage:
    python scripts/ingest_sample.py --limit 200 --qdrant http://localhost:6333
"""

from __future__ import annotations

import argparse
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLE_ACTS = [
    {"act_id": "WDU20230001", "title": "Kodeks pracy", "year": 2023, "publisher": "WDU"},
    {"act_id": "WDU20230002", "title": "Kodeks cywilny", "year": 2023, "publisher": "WDU"},
    {"act_id": "WDU20230003", "title": "Kodeks karny", "year": 2023, "publisher": "WDU"},
    {"act_id": "WDU20230004", "title": "Prawo administracyjne", "year": 2023, "publisher": "WDU"},
    {"act_id": "WDU20230005", "title": "Ustawa o podatku dochodowym", "year": 2023, "publisher": "WDU"},
    {"act_id": "SAOS100001", "title": "Wyrok NSA z dnia 2023-05-10", "year": 2023, "publisher": "ADMINISTRATIVE"},
    {"act_id": "SAOS100002", "title": "Wyrok SN z dnia 2023-06-15", "year": 2023, "publisher": "SUPREME"},
    {"act_id": "SAOS100003", "title": "Wyrok TK z dnia 2023-07-20", "year": 2023, "publisher": "CONSTITUTIONAL_TRIBUNAL"},
]

SAMPLE_TEXTS = [
    "Pracownik ma prawo do wynagrodzenia za pracę. Wynagrodzenie powinno być wypłacane co najmniej raz w miesiącu.",
    "Umowa o pracę zawierana jest na piśmie. Pracodawca jest obowiązany potwierdzić na piśmie ustalenia co do stron umowy.",
    "Wypowiedzenie umowy o pracę zawartej na czas nieokreślony jest uzasadnione, gdy pracownik naruszył obowiązki pracownicze.",
    "Właściciel nieruchomości może żądać, ażeby właściciel sąsiedniej nieruchomości zaniechał działań, które zakłócają korzystanie z nieruchomości.",
    "Zobowiązanie polega na tym, że wierzyciel może żądać od dłużnika świadczenia, a dłużnik powinien świadczenie spełnić.",
    "Kto zabiera w celu przywłaszczenia cudzą rzecz ruchomą, podlega karze pozbawienia wolności od 3 miesięcy do lat 5.",
    "Decyzja administracyjna powinna zawierać: oznaczenie organu administracji publicznej, datę wydania, oznaczenie strony.",
    "Podatnicy są obowiązani składać urzędom skarbowym zeznanie o wysokości osiągniętego dochodu w roku podatkowym.",
    "Skarga do sądu administracyjnego przysługuje od ostatecznych decyzji administracyjnych.",
    "Prawo do sądu obejmuje prawo dostępu do sądu, prawo do odpowiedniego ukształtowania procedury sądowej.",
    "Umowa sprzedaży zobowiązuje sprzedawcę do przeniesienia na kupującego własności rzeczy i wydania mu rzeczy.",
    "Pracodawca jest obowiązany udzielić pracownikowi urlopu wypoczynkowego w tym roku kalendarzowym, w którym pracownik uzyskał do niego prawo.",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="Liczba chunkow do ingestion")
    parser.add_argument("--qdrant", default="http://localhost:6333", help="Qdrant URL")
    parser.add_argument("--collection", default="lexcorpus", help="Nazwa kolekcji")
    parser.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    args = parser.parse_args()

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"Brakuje zaleznosci: {e}. Pomijam ingest_sample.", file=sys.stderr)
        sys.exit(0)

    print(f"Ladowanie modelu embeddingow: {args.model}")
    model = SentenceTransformer(args.model)
    dim = model.get_sentence_embedding_dimension()

    client = QdrantClient(url=args.qdrant, timeout=30)

    # Recreate collection
    try:
        client.delete_collection(args.collection)
    except Exception:
        pass

    client.create_collection(
        collection_name=args.collection,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )

    # Generate and ingest chunks
    points = []
    rng = random.Random(42)

    for i in range(args.limit):
        act = rng.choice(SAMPLE_ACTS)
        text = rng.choice(SAMPLE_TEXTS)
        chunk_index = i % 10

        vector = model.encode(text).tolist()
        payload = {
            "act_id": act["act_id"],
            "chunk_index": chunk_index,
            "title": act["title"],
            "year": act["year"],
            "publisher": act["publisher"],
            "text": text,
            "source_type": "legislation" if act["publisher"] == "WDU" else "judgment_nsa",
            "url": None,
            "section_type": "body",
        }
        points.append(qmodels.PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

    client.upsert(collection_name=args.collection, points=points)
    print(f"Zaingestionowano {len(points)} probnych chunkow do Qdrant ({args.qdrant})")


if __name__ == "__main__":
    main()
