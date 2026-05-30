"""
train_ner.py — Fine-tune HerBERT for Polish Legal NER.

Trains allegro/herbert-base-cased on the Polish Legal NER dataset.
If no labelled dataset exists, generates silver labels using the regex NER
from rag/ner.py as distant supervision (good enough for bootstrapping).

Output: output/herbert-legal-ner/  (compatible with rag/ner.py HerBERTLegalNER)

Entity labels (IOB2 scheme):
  B-PER / I-PER   — persons (judges, parties)
  B-LAW / I-LAW   — statute names
  B-ART / I-ART   — article references
  B-DAT / I-DAT   — dates
  B-CAS / I-CAS   — case IDs
  B-INS / I-INS   — institutions

Usage:
    # Bootstrap with silver labels from regex NER:
    python scripts/train_ner.py \\
        --input data/processed/chunks.jsonl \\
        --output output/herbert-legal-ner \\
        --max-chunks 5000 \\
        --silver-labels

    # Fine-tune on pre-existing CoNLL-format dataset:
    python scripts/train_ner.py \\
        --train-file data/ner/train.conll \\
        --dev-file data/ner/dev.conll \\
        --output output/herbert-legal-ner

Requirements:
    pip install transformers datasets seqeval torch
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

LABEL_LIST = ["O", "B-PER", "I-PER", "B-LAW", "I-LAW", "B-ART", "I-ART",
              "B-DAT", "I-DAT", "B-CAS", "I-CAS", "B-INS", "I-INS"]
LABEL2ID = {l: i for i, l in enumerate(LABEL_LIST)}
ID2LABEL = {i: l for l, i in LABEL2ID.items()}

ENTITY_TO_IOB = {
    "PERSON": "PER", "LAW": "LAW", "ARTICLE": "ART",
    "DATE": "DAT", "CASE_ID": "CAS", "INSTITUTION": "INS",
}


def _chunks_to_silver_conll(chunks: list[dict], max_chunks: int) -> list[list[tuple[str, str]]]:
    """Use regex NER to generate IOB2-tagged sentences from chunks (silver labels)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rag.ner import RegexLegalNER

    ner = RegexLegalNER()
    sentences: list[list[tuple[str, str]]] = []

    for chunk in chunks[:max_chunks]:
        text = chunk.get("text", "")[:600]
        if not text.strip():
            continue

        result = ner.extract(text)
        # Build char-level label array
        char_labels = ["O"] * len(text)
        for ent in result.entities:
            iob_base = ENTITY_TO_IOB.get(ent.label, "")
            if not iob_base:
                continue
            for i in range(ent.start, min(ent.end, len(text))):
                char_labels[i] = f"B-{iob_base}" if i == ent.start else f"I-{iob_base}"

        # Simple whitespace tokenizer → word-level labels (take label of first char)
        tokens = []
        for word in text.split():
            start = text.find(word)
            if start == -1:
                tokens.append((word, "O"))
            else:
                tokens.append((word, char_labels[start]))
                # Advance past found position to handle repeated words
                text = text[start + len(word):]
                char_labels = char_labels[start + len(word):]

        if tokens:
            sentences.append(tokens)

    log.info("Generated %d silver-labelled sentences", len(sentences))
    return sentences


def _read_conll(filepath: Path) -> list[list[tuple[str, str]]]:
    """Read CoNLL-format NER file (word \\t label per line, blank line = sentence end)."""
    sentences: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    with filepath.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line:
                if current:
                    sentences.append(current)
                    current = []
            else:
                parts = line.split()
                if len(parts) >= 2:
                    word, label = parts[0], parts[-1]
                    label = label if label in LABEL2ID else "O"
                    current.append((word, label))
    if current:
        sentences.append(current)
    return sentences


def _sentences_to_hf_dataset(sentences: list[list[tuple[str, str]]]):
    """Convert list of (word, label) sentences to HuggingFace Dataset format."""
    try:
        from datasets import Dataset
    except ImportError:
        log.error("datasets package required: pip install datasets")
        sys.exit(1)

    data = {"tokens": [], "ner_tags": []}
    for sent in sentences:
        tokens = [w for w, _ in sent]
        tags = [LABEL2ID.get(l, 0) for _, l in sent]
        data["tokens"].append(tokens)
        data["ner_tags"].append(tags)
    return Dataset.from_dict(data)


def train(
    train_sentences: list[list[tuple[str, str]]],
    dev_sentences: list[list[tuple[str, str]]],
    output_dir: str,
    model_name: str = "allegro/herbert-base-cased",
    num_train_epochs: int = 5,
    batch_size: int = 16,
    learning_rate: float = 3e-5,
) -> None:
    try:
        from transformers import (
            AutoModelForTokenClassification,
            AutoTokenizer,
            DataCollatorForTokenClassification,
            Trainer,
            TrainingArguments,
        )
        import numpy as np
        from seqeval.metrics import classification_report, f1_score
    except ImportError as e:
        log.error("Required packages missing: pip install transformers seqeval torch: %s", e)
        sys.exit(1)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=len(LABEL_LIST),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    train_ds = _sentences_to_hf_dataset(train_sentences)
    dev_ds = _sentences_to_hf_dataset(dev_sentences)

    def tokenize_and_align(examples):
        tokenized = tokenizer(
            examples["tokens"],
            is_split_into_words=True,
            truncation=True,
            max_length=256,
            padding=False,
        )
        labels_out = []
        for i, label_ids in enumerate(examples["ner_tags"]):
            word_ids = tokenized.word_ids(batch_index=i)
            prev_word_id = None
            label_seq = []
            for word_id in word_ids:
                if word_id is None:
                    label_seq.append(-100)
                elif word_id != prev_word_id:
                    label_seq.append(label_ids[word_id])
                else:
                    # Sub-word continuation — use I- variant if B- was previous
                    orig = label_ids[word_id]
                    orig_name = ID2LABEL.get(orig, "O")
                    if orig_name.startswith("B-"):
                        label_seq.append(LABEL2ID.get("I-" + orig_name[2:], orig))
                    else:
                        label_seq.append(orig)
                prev_word_id = word_id
            labels_out.append(label_seq)
        tokenized["labels"] = labels_out
        return tokenized

    train_ds = train_ds.map(tokenize_and_align, batched=True)
    dev_ds = dev_ds.map(tokenize_and_align, batched=True)

    def compute_metrics(p):
        logits, labels = p
        predictions = np.argmax(logits, axis=2)
        true_labels = [[ID2LABEL[l] for l in label if l != -100] for label in labels]
        pred_labels = [
            [ID2LABEL[p] for p, l in zip(prediction, label) if l != -100]
            for prediction, label in zip(predictions, labels)
        ]
        return {"f1": f1_score(true_labels, pred_labels)}

    collator = DataCollatorForTokenClassification(tokenizer)
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_train_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        warmup_ratio=0.1,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        logging_steps=50,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=dev_ds,
        tokenizer=tokenizer,
        data_collator=collator,
        compute_metrics=compute_metrics,
    )

    log.info("Training HerBERT NER on %d sentences …", len(train_sentences))
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    log.info("Model saved to %s", output_dir)

    # Final evaluation report
    preds, labels_all, _ = trainer.predict(dev_ds)
    pred_ids = preds.argmax(axis=2)
    true_labels = [[ID2LABEL[l] for l in label if l != -100] for label in labels_all]
    pred_labels = [
        [ID2LABEL[p] for p, l in zip(pred_row, lab_row) if l != -100]
        for pred_row, lab_row in zip(pred_ids, labels_all)
    ]
    print(classification_report(true_labels, pred_labels))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune HerBERT for Polish Legal NER")
    parser.add_argument("--input", type=Path, default=Path("data/processed/chunks.jsonl"),
                        help="Chunks JSONL for silver-label generation")
    parser.add_argument("--train-file", type=Path, default=None,
                        help="Pre-labelled CoNLL train file (skips silver generation)")
    parser.add_argument("--dev-file", type=Path, default=None, help="CoNLL dev file")
    parser.add_argument("--output", type=Path, default=Path("output/herbert-legal-ner"))
    parser.add_argument("--model", default="allegro/herbert-base-cased")
    parser.add_argument("--max-chunks", type=int, default=5000,
                        help="Max chunks to use for silver label generation")
    parser.add_argument("--silver-labels", action="store_true",
                        help="Generate silver labels from regex NER (no manual annotation needed)")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-5)
    args = parser.parse_args()

    if args.train_file and args.train_file.exists():
        log.info("Loading train/dev from CoNLL files …")
        train_sentences = _read_conll(args.train_file)
        dev_sentences = _read_conll(args.dev_file) if args.dev_file and args.dev_file.exists() else train_sentences[-max(1, len(train_sentences)//10):]
    elif args.silver_labels:
        log.info("Loading chunks for silver-label generation …")
        chunks = []
        with args.input.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        chunks.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        log.info("Loaded %d chunks", len(chunks))
        sentences = _chunks_to_silver_conll(chunks, args.max_chunks)
        split = max(1, int(len(sentences) * 0.9))
        train_sentences = sentences[:split]
        dev_sentences = sentences[split:]
    else:
        log.error("Provide --train-file or --silver-labels")
        sys.exit(1)

    log.info("Train: %d  Dev: %d sentences", len(train_sentences), len(dev_sentences))
    args.output.mkdir(parents=True, exist_ok=True)
    train(train_sentences, dev_sentences, str(args.output), args.model, args.epochs, args.batch_size, args.lr)


if __name__ == "__main__":
    main()
