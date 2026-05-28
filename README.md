# LexCorpus

**Polski system AI do odpowiadania na pytania prawne / Polish Legal AI Q&A System**

---

## Po polsku

### Opis projektu

LexCorpus to otwartoźródłowy projekt budowy systemu sztucznej inteligencji wyspecjalizowanego w polskim prawie. Celem jest stworzenie modelu językowego oraz systemu RAG (Retrieval-Augmented Generation), który odpowiada na pytania prawne lepiej niż ogólne modele takie jak GPT-4, dzięki fine-tuningowi na danych z Internetowego Systemu Aktów Prawnych (ISAP).

### Źródło danych

- **ISAP** (Internetowy System Aktów Prawnych): https://isap.sejm.gov.pl
- **API Sejmu RP**: https://api.sejm.gov.pl/eli/acts
- Dane obejmują: ustawy, rozporządzenia, dyrektywy, orzeczenia Trybunału Konstytucyjnego

### Architektura

```
ISAP API → fetch_isap.py → data/raw/*.jsonl
                         ↓
               preprocess.py → data/processed/chunks.jsonl
                         ↓
               build_dataset.py → HuggingFace Dataset (train/val/test)
                         ↓
               train.py (QLoRA) → output/lexcorpus-model
                         ↓
               ingest.py → Qdrant (wektory)
                         ↓
               api/main.py → POST /ask → odpowiedź + źródła
```

### Instalacja

```bash
pip install -e .
```

### Użycie

1. Pobierz dane z ISAP:
   ```bash
   python scripts/fetch_isap.py --year 2023 --output data/raw/
   ```

2. Wstępnie przetwórz dane:
   ```bash
   python scripts/preprocess.py --input data/raw/ --output data/processed/
   ```

3. Zbuduj dataset do fine-tuningu:
   ```bash
   python scripts/build_dataset.py --input data/processed/ --output data/dataset/
   ```

4. Fine-tuning (QLoRA):
   ```bash
   python training/train.py
   ```

5. Indeksuj dokumenty w Qdrant:
   ```bash
   python rag/ingest.py --input data/processed/chunks.jsonl
   ```

6. Uruchom API:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```

7. Zadaj pytanie:
   ```bash
   curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "Jakie są prawa pracownika przy wypowiedzeniu umowy o pracę?"}'
   ```

### Ewaluacja

```bash
python scripts/evaluate.py --model output/lexcorpus-model --dataset data/dataset/test
```

---

## In English

### Project Description

LexCorpus is an open-source Polish Legal AI system. The goal is to fine-tune a Polish language model (Bielik-7B) using QLoRA and build a RAG pipeline over Polish legal acts from ISAP — Poland's official legal database — to answer legal questions more accurately than general-purpose models like GPT-4.

### Data Sources

- **ISAP** (Internet System of Legal Acts): https://isap.sejm.gov.pl
- **Sejm REST API**: https://api.sejm.gov.pl/eli/acts
- Coverage: statutes, ordinances, constitutional tribunal rulings

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Data fetching | `httpx`, `bs4`, `lxml` |
| Preprocessing | custom chunker, ~512 tokens / chunk |
| Embeddings | `sdadas/mmlw-retrieval-roberta-large` |
| Vector store | Qdrant |
| Fine-tuning | QLoRA (r=16, α=32), PEFT + bitsandbytes |
| Base model | `speakleash/Bielik-7B-Instruct-v0.1` |
| API | FastAPI + Uvicorn |
| Evaluation | ROUGE, BERTScore, custom legal accuracy |

### Repository Structure

```
LexCorpus/
├── README.md
├── pyproject.toml
├── .gitignore
├── data/                     # raw + processed data (gitignored)
├── scripts/
│   ├── fetch_isap.py         # ISAP scraper
│   ├── preprocess.py         # text cleaner + chunker
│   ├── build_dataset.py      # HuggingFace Dataset builder
│   └── evaluate.py           # ROUGE / BERTScore / legal accuracy
├── training/
│   ├── config.yaml           # LoRA hyperparameters
│   └── train.py              # QLoRA training script
├── rag/
│   ├── ingest.py             # embed + store in Qdrant
│   └── retriever.py          # semantic search
├── api/
│   ├── main.py               # FastAPI application
│   └── schemas.py            # Pydantic models
└── notebooks/
    └── exploration.ipynb     # exploratory data analysis + RAG demo
```

### License

MIT License — see LICENSE file.

### Contributing

Pull requests welcome. Please open an issue first to discuss significant changes.
