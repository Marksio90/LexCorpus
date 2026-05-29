# LexCorpus

**Polski AI do prawa — RAG nad 636k dokumentami (ISAP + SAOS)**

> Cel: bić GPT-4o na polskich pytaniach prawnych dzięki data-moat + hybrid retrieval.

---

## Architektura

```
ISAP API  ──┐
SAOS API  ──┴─► preprocess ──► Qdrant (hybrid dense+sparse) ──► FastAPI ──► Next.js
```

**Jeden `docker compose up` robi wszystko** (sentinel files zapobiegają powtórnemu przetwarzaniu):

| Krok | Kontener | Co robi |
|------|----------|---------|
| 1 | `fetch` | Pobiera akty prawne z ISAP (JSONL) |
| 2 | `fetch-saos` | Pobiera orzeczenia z SAOS (JSONL) |
| 3 | `preprocess` | Chunking + wykrywanie sekcji SAOS → `chunks.jsonl` |
| 4 | `ingest` | Embedduje i ładuje do Qdrant; sentinel: `data/qdrant/.ingested` |
| 5 | `api` | FastAPI na :8000 |
| 6 | `frontend` | Next.js na :3000 |

---

## Szybki start

```bash
cp .env.example .env        # uzupełnij OPENAI_API_KEY
docker compose up
# → http://localhost:3000
```

---

## RAG pipeline

1. **Query expansion** — GPT-4o-mini generuje 2 alternatywne sformułowania
2. **Hybrid search** — dense (`mmlw-retrieval-roberta-large`) + sparse BM25, fusion RRF
3. **Dedup** — po `(act_id, chunk_index)`, najwyższy score wygrywa
4. **Cross-encoder rerank** — `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
5. **Context expand** — pobiera chunk±1 z Qdrant dla lepszego kontekstu

---

## Struktura katalogów

```
api/              FastAPI (main.py, schemas.py, sync.py)
rag/              retriever.py — hybrid search + rerank
                  ingest.py   — embed + store
scripts/
  fetch_isap.py       ISAP scraper
  fetch_saos.py       SAOS scraper
  preprocess.py       chunker + SAOS section detector
  run_eval.py         ewaluacja RAG na golden questions (45 pytań)
  generate_training_data.py  synteza danych Q&A przez GPT-4o-mini
  ingest_sample.py    CI helper — syntetyczne dane do testów
training/
  train.py            QLoRA fine-tuning (Bielik-7B / Mistral-7B)
  config.yaml         hiperparametry (r=16, 4-bit NF4)
frontend/         Next.js 14 + TypeScript
  app/ask/          chat z SSE streaming
  app/search/       wyszukiwanie dokumentów
  app/compare/      tryb porównania dwóch źródeł
  app/history/      historia zapytań (SQLite, per-user)
  app/upgrade/      strona cennikowa (Stripe)
  app/admin/        statystyki kolekcji + sync
  app/login/        magic-link auth (NextAuth)
nginx/            nginx.conf — reverse proxy dla produkcji
```

---

## API endpoints

| Method | Path | Opis |
|--------|------|------|
| `GET`  | `/health` | Status Qdrant + modeli |
| `POST` | `/ask` | RAG + LLM odpowiedź (JSON) |
| `POST` | `/ask/stream` | SSE: `sources → delta* → done\|error` |
| `POST` | `/search` | Samo wyszukiwanie (bez LLM) |
| `GET`  | `/stats` | Liczba chunków per publisher |
| `GET`  | `/sync/status` | Status auto-sync SAOS |
| `POST` | `/sync/trigger` | Ręczne wyzwolenie sync |

---

## Typy źródeł

| Typ | Publisher (Qdrant) | Źródło |
|-----|--------------------|--------|
| `legislation` | `WDU` | ISAP |
| `judgment_nsa` | `ADMINISTRATIVE` | SAOS |
| `judgment_sn` | `SUPREME` | SAOS |
| `judgment_tk` | `CONSTITUTIONAL_TRIBUNAL` | SAOS |
| `judgment_common` | `COMMON` | SAOS |
| `judgment_kio` | `NATIONAL_APPEAL_CHAMBER` | SAOS |

---

## Ewaluacja

```bash
python scripts/run_eval.py                   # retrieval + LLM
python scripts/run_eval.py --no-llm          # samo retrieval (szybkie)
python scripts/run_eval.py --compare-gpt4    # W/L/T vs GPT-4o baseline
```

45 pytań złotego zestawu: `data/eval_questions.jsonl` (30 legislacyjnych + 15 orzeczniczych).

---

## Fine-tuning (QLoRA na Bielik-7B)

```bash
# Krok 1 — dane syntetyczne (CPU, wymaga OPENAI_API_KEY, koszt ~$1.50)
python scripts/generate_training_data.py \
    --input data/processed/chunks.jsonl \
    --output data/dataset/synthetic \
    --max-chunks 5000

# Krok 2 — trening (GPU, min. 16GB VRAM)
docker compose run --rm train
```

---

## Tygodniowy sync SAOS

Automatyczny (APScheduler, domyślnie niedziela 03:00), lub ręcznie:

```bash
docker compose run --rm sync-saos
```

---

## Zmienne środowiskowe

Patrz `.env.example`. Kluczowe:

| Zmienna | Domyślnie | Opis |
|---------|-----------|------|
| `OPENAI_API_KEY` | — | Wymagane do LLM + query expansion |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model LLM |
| `EMBEDDING_MODEL` | `sdadas/mmlw-retrieval-roberta-large` | Dense embeddings |
| `RERANK_ENABLED` | `true` | Cross-encoder reranking |
| `STRIPE_SECRET_KEY` | — | Płatności (opcjonalne) |
| `DATABASE_PATH` | `prisma/dev.db` | SQLite — auth + historia |

---

## Produkcja

```bash
chmod +x deploy.sh && sudo ./deploy.sh
```

Nginx terminuje SSL. Overlay: `docker-compose.yml` + `docker-compose.prod.yml`.

---

## Licencja

MIT
