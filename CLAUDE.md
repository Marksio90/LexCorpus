# LexCorpus — Codebase Guide

Polish Legal AI: RAG over documents from ISAP (legislation), SAOS (court decisions), EUR-Lex (EU law), and KIS (tax interpretations).
Goal: beat GPT-4o on Polish legal questions using data-moat + hybrid retrieval.

## Architecture

```
ISAP API    ──┐
SAOS API    ──┤
EUR-Lex API ──┼─► preprocess ──► Qdrant (hybrid dense+sparse) ──► FastAPI ──► Next.js
KIS API     ──┘
                                  PostgreSQL (auth, history, users)
                                  Redis (result cache, Celery broker)
```

**Full pipeline on `docker compose up`** (one-shot services with sentinel files):
1. `fetch` — downloads ISAP legislation (JSONL)
2. `fetch-saos` — downloads SAOS judgments (JSONL)
3. `fetch-eurlex` — downloads EU regulations and directives from EUR-Lex
4. `fetch-kis` — downloads tax interpretations from KIS portal (Ministry of Finance)
5. `preprocess` — chunks text, outputs `data/processed/chunks.jsonl`
6. `ingest` — embeds chunks (dense + sparse BM25), loads into Qdrant; sentinel: `data/qdrant/.ingested`
7. `qdrant` — vector database (hybrid dense+sparse), internal network only
8. `postgres` — PostgreSQL for auth, question history, user data
9. `redis` — result cache + Celery broker
10. `worker` — Celery worker for async private document ingestion
11. `api` — FastAPI on :8000
12. `frontend` — Next.js on :3000

Profile-gated (not started by `docker compose up`):
- `train` — QLoRA fine-tuning; run: `docker compose run --rm train`
- `sync-saos` — manual SAOS sync; run: `docker compose run --rm sync-saos`

## Key directories

```
api/
  main.py              FastAPI entry point, CORS, global exception handler, Prometheus
  routers/
    ask.py             POST /ask, POST /ask/stream (SSE streaming)
    search.py          POST /search
    sync.py            GET /sync/status, POST /sync/trigger, GET /stats
    private.py         POST /ask/private, POST /internal/enqueue-document,
                       DELETE /private-collection/{user_id}
    agent.py           agent endpoints (plan, execute, tools)
  schemas.py           Pydantic models
  sync.py              APScheduler — weekly SAOS auto-sync
  rate_limit.py        token bucket per IP (Redis-backed; in-process fallback)
  result_cache.py      RAG result cache (Redis)
  dependencies.py      dependency injection (retriever, LLM provider, models)
  logging_config.py    JSON/text logging, GDPR question masking

rag/
  retriever.py         main pipeline: Adaptive RAG → expansion → HyDE → hybrid search → CRAG → rerank
  ingest.py            embed + store to Qdrant
  adaptive_rag.py      query complexity classifier (TRIVIAL / SIMPLE / COMPLEX)
  crag.py              Corrective RAG — filters low-score chunks before LLM
  colbert_retriever.py optional ColBERT reranker (lazy-loaded)
  agent.py             ReAct agent loop
  legal_graph.py       graph-based retrieval (experimental)
  raptor.py            RAPTOR hierarchical summarization (experimental)
  sat_graph.py         SAT-based reasoning graph (experimental)
  ner.py               NER for Polish legal acts

scripts/
  fetch_isap.py                   ISAP scraper
  fetch_saos.py                   SAOS scraper
  fetch_eurlex.py                 EUR-Lex scraper
  fetch_kis.py                    KIS scraper
  preprocess.py                   chunker + SAOS section detector
  run_eval.py                     RAG evaluation on golden question set
  generate_training_data.py       synthetic Q&A distillation (GPT-4o-mini → chat pairs)
  generate_contextual_chunks.py   Contextual Retrieval — LLM-enriched chunk prefixes

training/
  train.py             QLoRA fine-tuning, supports chat-format and legacy instruction-format
  config.yaml          hyperparameters (LoRA r=16, 4-bit NF4, Bielik-7B)
  Dockerfile.train     CUDA 12.1 container

frontend/     Next.js 14 app (app/, components/, lib/)
data/         raw/, processed/, qdrant/ (gitignored)
nginx/        nginx.conf for production reverse proxy
```

## RAG pipeline (rag/retriever.py)

1. **Adaptive RAG** — classifies query complexity; TRIVIAL skips retrieval, COMPLEX gets more candidates and expansions
2. **Query expansion** — GPT-4o-mini generates 2 alternative phrasings
3. **HyDE** — generates a hypothetical document to broaden query semantics
4. **Hybrid search** — dense (`sdadas/mmlw-retrieval-roberta-large-v2`) + sparse BM25 fused with RRF
5. **CRAG** — cross-encoder pre-filter: drops chunks below `CRAG_LOW_THRESHOLD` score
6. **Dedup** — by `(act_id, chunk_index)`, keep highest score
7. **Cross-encoder rerank** — `sdadas/polish-reranker-large-ranknet` (best Polish reranker, PIRB NDCG@10: 62.65)
8. **ColBERT rerank** — optional, lazy-loaded via `COLBERT_ENABLED`
9. **Context expand** — fetches chunk±1 from Qdrant for surrounding context

## API endpoints (api/main.py + routers/)

- `GET  /ping` — lightweight liveness probe (no external calls)
- `GET  /health` — Qdrant + model readiness check (returns 503 if Qdrant down)
- `POST /ask` — RAG + LLM answer (JSON)
- `POST /ask/stream` — SSE stream: `sources → delta* → done|error`
- `POST /ask/private` — RAG over user's private collection
- `POST /search` — pure retrieval (no LLM)
- `GET  /stats` — chunk count per publisher
- `GET  /sync/status` — SAOS auto-sync status
- `POST /sync/trigger` — manual sync trigger
- `POST /internal/enqueue-document` — queue private doc for Celery ingestion
- `DELETE /private-collection/{user_id}` — delete user's private collection
- `POST /agent/*` — agent endpoints (plan, execute, tools)
- `GET  /metrics` — Prometheus metrics (if `prometheus-fastapi-instrumentator` installed)

Rate limiting: Redis-backed token bucket per IP (`RATE_LIMIT_REQUESTS/RATE_LIMIT_WINDOW`); falls back to in-process when Redis is unavailable. **In-process fallback is not shared across multiple API workers — use Redis in multi-worker deployments.**

CORS: `ALLOWED_ORIGINS` env var (comma-separated). **`allow_credentials=True` is incompatible with `*` in browsers — always use a specific domain in production.**

## Source types

| SourceType            | Publisher (Qdrant)         | Origin  |
|-----------------------|----------------------------|---------|
| `legislation`         | `WDU`                      | ISAP    |
| `judgment_nsa`        | `ADMINISTRATIVE`           | SAOS    |
| `judgment_sn`         | `SUPREME`                  | SAOS    |
| `judgment_tk`         | `CONSTITUTIONAL_TRIBUNAL`  | SAOS    |
| `judgment_common`     | `COMMON`                   | SAOS    |
| `judgment_kio`        | `NATIONAL_APPEAL_CHAMBER`  | SAOS    |
| `eu_regulation`       | `EURLEX`                   | EUR-Lex |
| `tax_interpretation`  | `KIS`                      | KIS     |

## Frontend (Next.js 14, TypeScript)

Key routes in `frontend/app/`:
- `/ask` — chat with SSE streaming, source filter pills
- `/search` — document search with type filters and result count selector
- `/compare` — side-by-side source comparison
- `/analyze` — document analysis
- `/draft` — legal document drafting assistant
- `/expert` — expert consultation requests
- `/precedents` — precedent search
- `/timeline/[actId]` — legislative change timeline
- `/alerts` — regulatory change alerts
- `/analytics` — usage analytics
- `/registry` — act registry + subscriptions
- `/history` — question history (per-user, PostgreSQL)
- `/account/*` — settings, API tokens, private documents, widget config
- `/admin` — collection stats, sync controls, feedback export
- `/upgrade` — pricing page (Stripe)
- `/onboarding` — onboarding flow
- `/login` — magic-link auth (NextAuth)
- `/share/[token]` — shared answer pages
- `/widget/[token]` — embeddable iframe widget

Key components: `AskForm`, `AnswerCard` (renders `[N]` citation badges), `SourceList` (type badges), `Sidebar`.

## Evaluation (scripts/run_eval.py)

```bash
python scripts/run_eval.py                        # retrieval + LLM scoring
python scripts/run_eval.py --no-llm               # retrieval only (fast)
python scripts/run_eval.py --compare-gpt4         # W/L/T vs GPT-4o baseline
```

Questions in `data/eval_questions.jsonl` (45 questions: 30 legislation + 15 jurisprudence).

## Environment variables

See `.env.example` for all variables. Key ones:

| Variable               | Default                                    | Purpose                           |
|------------------------|--------------------------------------------|-----------------------------------|
| `OPENAI_API_KEY`       | —                                          | Required for LLM + expansion      |
| `OPENAI_MODEL`         | `gpt-4o-mini`                              | LLM model                         |
| `EMBEDDING_MODEL`      | `sdadas/mmlw-retrieval-roberta-large-v2`   | Dense embeddings                  |
| `RERANK_MODEL`         | `sdadas/polish-reranker-large-ranknet`     | Cross-encoder reranker            |
| `RERANK_ENABLED`       | `true`                                     | Cross-encoder reranking           |
| `EXPAND_ENABLED`       | `true`                                     | Query expansion                   |
| `HYDE_ENABLED`         | `true`                                     | Hypothetical Document Embedding   |
| `CRAG_ENABLED`         | `true`                                     | Corrective RAG chunk filter       |
| `ADAPTIVE_RAG_ENABLED` | `true`                                     | Query complexity routing          |
| `POSTGRES_PASSWORD`    | —                                          | PostgreSQL password (required)    |
| `DATABASE_URL`         | `postgresql://lexcorpus:...@postgres:5432` | PostgreSQL connection string      |
| `REDIS_URL`            | `redis://redis:6379/0`                     | Redis — cache + Celery broker     |
| `QDRANT_API_KEY`       | —                                          | Qdrant API key (required)         |
| `INTERNAL_API_SECRET`  | —                                          | Next.js ↔ FastAPI secret (required)|
| `ALLOWED_ORIGINS`      | `https://lexcorpus.app`                    | CORS origins (never `*` in prod)  |
| `RATE_LIMIT_REQUESTS`  | `20`                                       | Requests per IP per window        |
| `RATE_LIMIT_WINDOW`    | `60`                                       | Window in seconds                 |
| `SAOS_ENABLED`         | `true`                                     | Fetch court judgments             |
| `EURLEX_ENABLED`       | `true`                                     | Fetch EUR-Lex acts                |
| `KIS_ENABLED`          | `true`                                     | Fetch KIS tax interpretations     |
| `FETCH_YEAR_FROM/TO`   | `2018/2025`                                | ISAP legislation year range       |
| `NEXTAUTH_SECRET`      | —                                          | NextAuth secret (required)        |

## Production deployment

```bash
chmod +x deploy.sh && sudo ./deploy.sh
```

Uses `docker-compose.yml` + `docker-compose.prod.yml` overlay. Nginx terminates SSL.

## Fine-tuning (QLoRA on Bielik-7B)

### Step 1 — synthetic data generation (CPU, requires OPENAI_API_KEY)
```bash
python scripts/generate_training_data.py \
    --input data/processed/chunks.jsonl \
    --output data/dataset/synthetic \
    --max-chunks 5000 \
    --questions-per-chunk 2
# Cost: ~5000 * 2 * $0.00015 ≈ $1.50 with gpt-4o-mini
# Output: data/dataset/synthetic/train.jsonl (chat-format, ~10k records)
```

### Step 2 — training (GPU, min. 16GB VRAM)
```bash
python training/train.py --data data/dataset/synthetic/train.jsonl
# or via Docker (GPU):
docker compose run --rm train
```

### Step 3 — deployment
```bash
# Set LOCAL_MODEL_PATH in .env to the merged model directory:
LOCAL_MODEL_PATH=./output/lexcorpus-merged
```

Files:
- `scripts/generate_training_data.py` — synthetic data distillation (GPT-4o-mini → chat pairs)
- `training/train.py` — QLoRA fine-tuning, supports chat-format and legacy instruction-format
- `training/config.yaml` — hyperparameters (LoRA r=16, 4-bit NF4, Bielik-7B)
- `Dockerfile.train` — CUDA 12.1 training container

## Weekly SAOS sync

```bash
docker compose run --rm sync-saos
```
