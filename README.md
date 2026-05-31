# LexCorpus

**Polski AI do prawa — RAG nad dokumentami ISAP, SAOS, EUR-Lex i KIS**

> Cel: bić GPT-4o na polskich pytaniach prawnych dzięki data-moat + hybrid retrieval.

---

## Architektura

```
ISAP API    ──┐
SAOS API    ──┤
EUR-Lex API ──┼─► preprocess ──► Qdrant (hybrid dense+sparse) ──► FastAPI ──► Next.js
KIS API     ──┘
                                  PostgreSQL (auth, historia)
                                  Redis (cache, kolejka Celery)
```

**Jeden `docker compose up` robi wszystko** (sentinel files zapobiegają powtórnemu przetwarzaniu):

| Krok | Kontener | Co robi |
|------|----------|---------|
| 1 | `fetch` | Pobiera akty prawne z ISAP (JSONL) |
| 2 | `fetch-saos` | Pobiera orzeczenia z SAOS (JSONL) |
| 3 | `fetch-eurlex` | Pobiera rozporządzenia i dyrektywy UE z EUR-Lex |
| 4 | `fetch-kis` | Pobiera interpretacje podatkowe z portalu KIS (MF) |
| 5 | `preprocess` | Chunking + wykrywanie sekcji → `chunks.jsonl` |
| 6 | `ingest` | Embedduje i ładuje do Qdrant; sentinel: `data/qdrant/.ingested` |
| 7 | `qdrant` | Wektorowa baza danych (hybrid dense+sparse) |
| 8 | `postgres` | PostgreSQL — auth, historia zapytań, dane użytkowników |
| 9 | `redis` | Cache wyników, broker kolejki Celery |
| 10 | `worker` | Celery worker — przetwarzanie prywatnych dokumentów async |
| 11 | `api` | FastAPI na :8000 |
| 12 | `frontend` | Next.js na :3000 |

Profile-only (nie startują przy `docker compose up`):

| Profil | Kontener | Uruchomienie |
|--------|----------|--------------|
| `train` | `train` | `docker compose run --rm train` |
| `sync` | `sync-saos` | `docker compose run --rm sync-saos` |

---

## Szybki start

```bash
cp .env.example .env        # uzupełnij OPENAI_API_KEY, POSTGRES_PASSWORD, QDRANT_API_KEY, INTERNAL_API_SECRET
docker compose up
# → http://localhost:3000
```

---

## RAG pipeline

1. **Adaptive RAG** — klasyfikuje złożoność zapytania; TRIVIAL pomija retrieval, COMPLEX dostaje więcej kandydatów
2. **Query expansion** — GPT-4o-mini generuje 2 alternatywne sformułowania
3. **HyDE** — generuje hipotetyczny dokument by rozszerzyć semantykę zapytania
4. **Hybrid search** — dense (`sdadas/mmlw-retrieval-roberta-large-v2`) + sparse BM25, fusion RRF
5. **CRAG (Corrective RAG)** — filtruje chunki o niskim score przed LLM (zapobiega cytowaniu złych ustaw)
6. **Dedup** — po `(act_id, chunk_index)`, najwyższy score wygrywa
7. **Cross-encoder rerank** — `sdadas/polish-reranker-large-ranknet` (PIRB NDCG@10: 62.65)
8. **ColBERT rerank** — opcjonalny, ładowany leniwie
9. **Context expand** — pobiera chunk±1 z Qdrant dla lepszego kontekstu

---

## Struktura katalogów

```
api/
  main.py              punkt wejścia FastAPI, CORS, exception handler, Prometheus
  routers/
    ask.py             POST /ask, POST /ask/stream (SSE)
    search.py          POST /search
    sync.py            GET /sync/status, POST /sync/trigger, GET /stats
    private.py         POST /ask/private, POST /internal/enqueue-document
    agent.py           endpointy agentowe (plan, execute, tools)
  schemas.py           modele Pydantic
  sync.py              APScheduler — tygodniowy sync SAOS
  rate_limit.py        token bucket per IP (Redis-backed, fallback in-process)
  result_cache.py      cache wyników RAG (Redis)
  dependencies.py      dependency injection (retriever, LLM, modele)

rag/
  retriever.py         hybrid search + HyDE + CRAG + Adaptive RAG + rerank
  ingest.py            embed + store do Qdrant
  adaptive_rag.py      klasyfikacja złożoności zapytania
  crag.py              Corrective RAG
  colbert_retriever.py opcjonalny reranker ColBERT
  agent.py             agent loop (ReAct)
  legal_graph.py       graph-based retrieval (eksperymentalny)
  raptor.py            RAPTOR hierarchical summarization (eksperymentalny)
  sat_graph.py         SAT-based reasoning graph (eksperymentalny)
  ner.py               NER dla polskich aktów prawnych

scripts/
  fetch_isap.py                   ISAP scraper
  fetch_saos.py                   SAOS scraper
  fetch_eurlex.py                 EUR-Lex scraper
  fetch_kis.py                    KIS scraper (interpretacje podatkowe MF)
  preprocess.py                   chunker + sekcje SAOS
  run_eval.py                     ewaluacja RAG (45 pytań golden set)
  generate_training_data.py       synteza danych Q&A przez GPT-4o-mini
  generate_contextual_chunks.py   Contextual Retrieval — enrichment chunków LLM

training/
  train.py             QLoRA fine-tuning (Bielik-7B / Mistral-7B)
  config.yaml          hiperparametry (r=16, 4-bit NF4)

frontend/              Next.js 14 + TypeScript + Tailwind
  app/ask/             chat z SSE streaming, filtry źródeł
  app/search/          wyszukiwanie dokumentów, filtry typu i liczby wyników
  app/compare/         porównanie dwóch źródeł
  app/analyze/         analiza dokumentu
  app/draft/           asystent drafting dokumentów prawnych
  app/expert/          zlecenia eksperckie
  app/precedents/      wyszukiwanie precedensów
  app/timeline/        oś czasu zmian aktu prawnego
  app/alerts/          alerty na zmiany w przepisach
  app/analytics/       statystyki użytkowania
  app/registry/        rejestr aktów + subskrypcje
  app/history/         historia zapytań (per-user, PostgreSQL)
  app/account/         ustawienia, API-tokeny, dokumenty prywatne, widget
  app/admin/           statystyki kolekcji, sync, feedback
  app/upgrade/         cennik (Stripe)
  app/onboarding/      onboarding
  app/login/           magic-link auth (NextAuth)
  app/share/[token]/   współdzielone odpowiedzi
  app/widget/[token]/  embeddowalny widget (iframe)

nginx/                 nginx.conf — reverse proxy dla produkcji
```

---

## API endpoints

| Method | Ścieżka | Opis |
|--------|---------|------|
| `GET`  | `/ping` | Liveness probe — bez external calls |
| `GET`  | `/health` | Readiness check — Qdrant + modele |
| `POST` | `/ask` | RAG + LLM odpowiedź (JSON) |
| `POST` | `/ask/stream` | SSE: `sources → delta* → done\|error` |
| `POST` | `/ask/private` | RAG nad prywatną kolekcją użytkownika |
| `POST` | `/search` | Samo wyszukiwanie (bez LLM) |
| `GET`  | `/stats` | Liczba chunków per publisher |
| `GET`  | `/sync/status` | Status auto-sync SAOS |
| `POST` | `/sync/trigger` | Ręczne wyzwolenie sync |
| `POST` | `/internal/enqueue-document` | Kolejkuje dokument prywatny do Celery |
| `DELETE` | `/private-collection/{user_id}` | Usuwa prywatną kolekcję |
| `POST` | `/agent/*` | Endpointy agentowe (plan, execute, tools) |
| `GET`  | `/metrics` | Prometheus metrics (jeśli zainstalowany) |

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
| `eu_regulation` | `EURLEX` | EUR-Lex |
| `tax_interpretation` | `KIS` | KIS (MF) |

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
    --max-chunks 5000 \
    --questions-per-chunk 2

# Krok 2 — trening (GPU, min. 16GB VRAM)
docker compose run --rm train

# Krok 3 — deployment: ustaw LOCAL_MODEL_PATH w .env
LOCAL_MODEL_PATH=./output/lexcorpus-merged
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
| `EMBEDDING_MODEL` | `sdadas/mmlw-retrieval-roberta-large-v2` | Dense embeddings |
| `RERANK_MODEL` | `sdadas/polish-reranker-large-ranknet` | Cross-encoder reranker |
| `RERANK_ENABLED` | `true` | Cross-encoder reranking |
| `EXPAND_ENABLED` | `true` | Query expansion |
| `HYDE_ENABLED` | `true` | Hypothetical Document Embedding |
| `CRAG_ENABLED` | `true` | Corrective RAG (filtr niskiego score) |
| `ADAPTIVE_RAG_ENABLED` | `true` | Klasyfikacja złożoności zapytania |
| `POSTGRES_USER` | `lexcorpus` | Użytkownik PostgreSQL |
| `POSTGRES_PASSWORD` | — | Hasło PostgreSQL (wymagane) |
| `DATABASE_URL` | `postgresql://...` | Connection string PostgreSQL |
| `REDIS_URL` | `redis://redis:6379/0` | Redis — cache + Celery broker |
| `QDRANT_API_KEY` | — | Klucz API Qdrant (wymagany) |
| `INTERNAL_API_SECRET` | — | Sekret Next.js ↔ FastAPI (wymagany) |
| `ALLOWED_ORIGINS` | `https://lexcorpus.app` | CORS — nigdy `*` na produkcji przy `allow_credentials=True` |
| `RATE_LIMIT_REQUESTS` | `20` | Maks. requestów per IP per okno |
| `RATE_LIMIT_WINDOW` | `60` | Okno rate limitingu (sekundy) |
| `SAOS_ENABLED` | `true` | Pobieranie orzeczeń SAOS |
| `EURLEX_ENABLED` | `true` | Pobieranie aktów EUR-Lex |
| `KIS_ENABLED` | `true` | Pobieranie interpretacji KIS |
| `FETCH_YEAR_FROM/TO` | `2018/2025` | Zakres lat dla ISAP |
| `NEXTAUTH_SECRET` | — | Sekret NextAuth (wymagany) |
| `STRIPE_SECRET_KEY` | — | Płatności Stripe (opcjonalne) |

---

## Produkcja

```bash
chmod +x deploy.sh && sudo ./deploy.sh
```

Nginx terminuje SSL. Overlay: `docker-compose.yml` + `docker-compose.prod.yml`.

---

## Licencja

MIT
