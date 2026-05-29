# LexCorpus — Codebase Guide

Polish Legal AI: RAG over ~636k documents (ISAP legislation + SAOS court decisions).
Goal: beat GPT-4o on Polish legal questions using data-moat + hybrid retrieval.

## Architecture

```
ISAP API  ──┐
SAOS API  ──┤─► preprocess ──► Qdrant (hybrid dense+sparse) ──► FastAPI ──► Next.js
            └── chunks.jsonl
```

**Full pipeline on `docker compose up`** (one-shot services with sentinel files):
1. `fetch` — downloads ISAP legislation (JSONL)
2. `fetch-saos` — downloads SAOS judgments (JSONL)
3. `preprocess` — chunks text, outputs `data/processed/chunks.jsonl`
4. `ingest` — embeds chunks (dense BM25+sparse), loads into Qdrant; sentinel: `data/qdrant/.ingested`
5. `api` — FastAPI on :8000
6. `frontend` — Next.js on :3000

## Key directories

```
api/          FastAPI app (main.py, schemas.py)
rag/          retriever.py (hybrid search + rerank), ingest.py
scripts/      fetch_isap.py, fetch_saos.py, preprocess.py, run_eval.py
frontend/     Next.js 14 app (app/, components/, lib/)
data/         raw/, processed/, qdrant/ (gitignored)
nginx/        nginx.conf for production reverse proxy
```

## RAG pipeline (rag/retriever.py)

1. **Query expansion** — GPT-4o-mini generates 2 alternative phrasings
2. **Hybrid search** — dense (mmlw-retrieval-roberta-large) + sparse BM25 fused with RRF
3. **Dedup** — by `(act_id, chunk_index)`, keep highest score
4. **Cross-encoder rerank** — `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`

## API endpoints (api/main.py)

- `GET  /health` — Qdrant + model status
- `POST /ask` — RAG + LLM answer (JSON)
- `POST /ask/stream` — SSE stream: `sources → delta* → done|error`
- `POST /search` — pure retrieval (no LLM)

Rate limiting: in-process token bucket per IP (`RATE_LIMIT_REQUESTS/RATE_LIMIT_WINDOW`).
CORS: `ALLOWED_ORIGINS` env var (comma-separated; `*` for dev).

## Source types

| SourceType          | Publisher (Qdrant)         | Origin  |
|---------------------|----------------------------|---------|
| `legislation`       | `WDU`                      | ISAP    |
| `judgment_nsa`      | `ADMINISTRATIVE`           | SAOS    |
| `judgment_sn`       | `SUPREME`                  | SAOS    |
| `judgment_tk`       | `CONSTITUTIONAL_TRIBUNAL`  | SAOS    |
| `judgment_common`   | `COMMON`                   | SAOS    |
| `judgment_kio`      | `NATIONAL_APPEAL_CHAMBER`  | SAOS    |

## Frontend (Next.js 14, TypeScript)

- `/ask` — chat interface with source filter pills and streaming
- `/search` — pure document search with type filters and result count selector
- `/history` — local-storage question history
- `/admin` — collection stats

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

| Variable             | Default                              | Purpose                        |
|----------------------|--------------------------------------|--------------------------------|
| `OPENAI_API_KEY`     | —                                    | Required for LLM + expansion   |
| `OPENAI_MODEL`       | `gpt-4o-mini`                        | LLM model                      |
| `EMBEDDING_MODEL`    | `sdadas/mmlw-retrieval-roberta-large`| Dense embeddings               |
| `RERANK_ENABLED`     | `true`                               | Cross-encoder reranking        |
| `EXPAND_ENABLED`     | `true`                               | Query expansion                |
| `ALLOWED_ORIGINS`    | `*`                                  | CORS origins (use domain prod) |
| `RATE_LIMIT_REQUESTS`| `20`                                 | Requests per IP per window     |
| `RATE_LIMIT_WINDOW`  | `60`                                 | Window in seconds              |
| `SAOS_ENABLED`       | `true`                               | Fetch court judgments          |
| `FETCH_YEAR_FROM/TO` | `2024/2025`                          | ISAP legislation years         |

## Production deployment

```bash
chmod +x deploy.sh && sudo ./deploy.sh
```

Uses `docker-compose.yml` + `docker-compose.prod.yml` overlay. Nginx terminates SSL.

## Fine-tuning (QLoRA na Bielik-7B)

### Krok 1 — generowanie danych syntetycznych (CPU, wymaga OPENAI_API_KEY)
```bash
python scripts/generate_training_data.py \
    --input data/processed/chunks.jsonl \
    --output data/dataset/synthetic \
    --max-chunks 5000 \
    --questions-per-chunk 2
# Koszt: ~5000 * 2 * $0.00015 ≈ $1.50 przy gpt-4o-mini
# Wynik: data/dataset/synthetic/train.jsonl (chat-format, ~10k rekordów)
```

### Krok 2 — trening (GPU, min. 16GB VRAM)
```bash
python training/train.py --data data/dataset/synthetic/train.jsonl
# lub przez Docker (GPU):
docker compose run --rm train
```

### Krok 3 — deployment
```bash
# Ustaw LOCAL_MODEL_PATH w .env na katalog z wytrenowanym modelem:
LOCAL_MODEL_PATH=./output/lexcorpus-merged
```

Pliki:
- `scripts/generate_training_data.py` — syntetic data distillation (GPT-4o-mini → chat pairs)
- `training/train.py` — QLoRA fine-tuning, obsługuje chat-format i legacy instruction-format
- `training/config.yaml` — hiperparametry (LoRA r=16, 4-bit NF4, Bielik-7B)
- `Dockerfile.train` — kontener CUDA 12.1 do trenowania

## Weekly SAOS sync

```bash
docker compose run --rm sync-saos
```
