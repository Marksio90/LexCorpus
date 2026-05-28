"""
evaluate.py — Evaluation script for LexCorpus model outputs.

Metrics:
  - ROUGE-1, ROUGE-2, ROUGE-L  (lexical overlap)
  - BERTScore F1               (semantic similarity)
  - Legal accuracy             (custom: checks key legal terms / citations)

Usage:
    python scripts/evaluate.py --predictions preds.jsonl --references refs.jsonl
    python scripts/evaluate.py --model output/lexcorpus-model --dataset data/dataset/test
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
from datasets import load_from_disk
from rouge_score import rouge_scorer
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# Polish legal terms used in accuracy check
LEGAL_TERMS_PL = [
    "ustawa", "rozporządzenie", "artykuł", "paragraf", "przepis", "kodeks",
    "prawo", "obowiązek", "uprawnienie", "odpowiedzialność", "kara", "sankcja",
    "wyrok", "orzeczenie", "sąd", "trybunał", "minister", "organ", "podmiot",
    "strona", "powód", "pozwany", "wnioskodawca", "pełnomocnik", "adwokat",
    "radca", "notariusz", "prokuratura", "prokurator", "zarzut", "dowód",
]

# Citation patterns in Polish law (e.g. "art. 5 ust. 2", "§ 3 pkt 1")
CITATION_PATTERN = re.compile(
    r"(art(?:ykuł)?\.?\s+\d+[a-z]?(?:\s+ust\.\s+\d+)?|§\s*\d+[a-z]?(?:\s+pkt\s+\d+)?)",
    re.IGNORECASE,
)


class MetricsResult(NamedTuple):
    rouge1: float
    rouge2: float
    rougeL: float
    bertscore_f1: float
    legal_term_recall: float
    citation_precision: float
    n_samples: int

    def as_dict(self) -> dict:
        return {
            "rouge1": round(self.rouge1, 4),
            "rouge2": round(self.rouge2, 4),
            "rougeL": round(self.rougeL, 4),
            "bertscore_f1": round(self.bertscore_f1, 4),
            "legal_term_recall": round(self.legal_term_recall, 4),
            "citation_precision": round(self.citation_precision, 4),
            "n_samples": self.n_samples,
        }


def compute_rouge(predictions: list[str], references: list[str]) -> dict[str, float]:
    """Compute ROUGE-1, ROUGE-2, ROUGE-L scores."""
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=False)
    r1_scores, r2_scores, rL_scores = [], [], []

    for pred, ref in zip(predictions, references):
        scores = scorer.score(ref, pred)
        r1_scores.append(scores["rouge1"].fmeasure)
        r2_scores.append(scores["rouge2"].fmeasure)
        rL_scores.append(scores["rougeL"].fmeasure)

    return {
        "rouge1": float(np.mean(r1_scores)),
        "rouge2": float(np.mean(r2_scores)),
        "rougeL": float(np.mean(rL_scores)),
    }


def compute_bertscore(predictions: list[str], references: list[str], lang: str = "pl") -> float:
    """Compute BERTScore F1 using multilingual BERT."""
    try:
        from bert_score import score as bert_score_fn

        _, _, f1 = bert_score_fn(
            predictions,
            references,
            lang=lang,
            verbose=False,
            rescale_with_baseline=False,
        )
        return float(f1.mean().item())
    except ImportError:
        log.warning("bert-score not installed; skipping BERTScore computation")
        return 0.0
    except Exception as exc:
        log.warning("BERTScore failed: %s", exc)
        return 0.0


def compute_legal_term_recall(predictions: list[str], references: list[str]) -> float:
    """
    Custom legal accuracy metric:
    Measures what fraction of legal terms present in the reference
    are also present in the prediction (recall over legal vocabulary).
    """
    recalls = []
    for pred, ref in zip(predictions, references):
        ref_lower = ref.lower()
        pred_lower = pred.lower()
        ref_terms = [t for t in LEGAL_TERMS_PL if t in ref_lower]
        if not ref_terms:
            recalls.append(1.0)
            continue
        found = sum(1 for t in ref_terms if t in pred_lower)
        recalls.append(found / len(ref_terms))
    return float(np.mean(recalls)) if recalls else 0.0


def compute_citation_precision(predictions: list[str], references: list[str]) -> float:
    """
    Custom citation accuracy metric:
    Of legal citations (art. X, § Y) in the prediction,
    what fraction also appear in the reference?
    High precision means the model isn't hallucinating citations.
    """
    precisions = []
    for pred, ref in zip(predictions, references):
        pred_citations = set(c.lower() for c in CITATION_PATTERN.findall(pred))
        if not pred_citations:
            precisions.append(1.0)
            continue
        ref_citations = set(c.lower() for c in CITATION_PATTERN.findall(ref))
        correct = len(pred_citations & ref_citations)
        precisions.append(correct / len(pred_citations))
    return float(np.mean(precisions)) if precisions else 1.0


def generate_predictions_from_model(
    model_path: str,
    dataset_path: str,
    max_new_tokens: int = 256,
    batch_size: int = 4,
) -> tuple[list[str], list[str]]:
    """Load model and generate predictions on the test dataset."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    log.info("Loading model from %s …", model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    model.eval()

    log.info("Loading test dataset from %s …", dataset_path)
    ds = load_from_disk(dataset_path)
    if hasattr(ds, "__getitem__") and "test" in ds:
        ds = ds["test"]

    predictions = []
    references = []

    for i in tqdm(range(0, len(ds), batch_size), desc="Generating", unit="batch"):
        batch = ds[i : i + batch_size]
        instructions = batch["instruction"] if isinstance(batch["instruction"], list) else [batch["instruction"]]
        inputs_text = batch["input"] if isinstance(batch["input"], list) else [batch["input"]]
        outputs_ref = batch["output"] if isinstance(batch["output"], list) else [batch["output"]]

        prompts = [
            f"### Instrukcja:\n{instr}\n\n### Przepis:\n{inp}\n\n### Odpowiedź:\n"
            for instr, inp in zip(instructions, inputs_text)
        ]

        encoded = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=1024)
        encoded = {k: v.to(model.device) for k, v in encoded.items()}

        with torch.no_grad():
            output_ids = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        for j, ids in enumerate(output_ids):
            input_len = encoded["input_ids"].shape[1]
            pred_ids = ids[input_len:]
            pred_text = tokenizer.decode(pred_ids, skip_special_tokens=True).strip()
            predictions.append(pred_text)
            references.append(outputs_ref[j])

    return predictions, references


def evaluate(predictions: list[str], references: list[str]) -> MetricsResult:
    """Compute all metrics for a set of predictions vs references."""
    log.info("Computing ROUGE scores …")
    rouge = compute_rouge(predictions, references)

    log.info("Computing BERTScore …")
    bs_f1 = compute_bertscore(predictions, references)

    log.info("Computing legal accuracy metrics …")
    term_recall = compute_legal_term_recall(predictions, references)
    cite_precision = compute_citation_precision(predictions, references)

    return MetricsResult(
        rouge1=rouge["rouge1"],
        rouge2=rouge["rouge2"],
        rougeL=rouge["rougeL"],
        bertscore_f1=bs_f1,
        legal_term_recall=term_recall,
        citation_precision=cite_precision,
        n_samples=len(predictions),
    )


def load_jsonl_pairs(predictions_path: Path, references_path: Path) -> tuple[list[str], list[str]]:
    """Load predictions and references from JSONL files."""
    def read_outputs(path: Path) -> list[str]:
        results = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                # Accept "output", "answer", "prediction", "text" as output field
                for key in ("output", "answer", "prediction", "text"):
                    if key in rec:
                        results.append(rec[key])
                        break
        return results

    preds = read_outputs(predictions_path)
    refs = read_outputs(references_path)
    if len(preds) != len(refs):
        log.warning(
            "Predictions (%d) and references (%d) have different lengths; truncating to shorter",
            len(preds),
            len(refs),
        )
    n = min(len(preds), len(refs))
    return preds[:n], refs[:n]


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate LexCorpus model performance.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--model", type=str, help="Path to fine-tuned model for inference")
    group.add_argument("--predictions", type=Path, help="JSONL file with prediction outputs")

    parser.add_argument("--dataset", type=str, help="Path to HuggingFace dataset (used with --model)")
    parser.add_argument("--references", type=Path, help="JSONL file with reference outputs (used with --predictions)")
    parser.add_argument("--output", type=Path, default=None, help="Save JSON results to this path")
    parser.add_argument("--max-samples", type=int, default=None, help="Limit evaluation to N samples")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()

    if args.model:
        if not args.dataset:
            log.error("--dataset is required when using --model")
            sys.exit(1)
        predictions, references = generate_predictions_from_model(
            args.model,
            args.dataset,
            max_new_tokens=args.max_new_tokens,
            batch_size=args.batch_size,
        )
    else:
        if not args.references:
            log.error("--references is required when using --predictions")
            sys.exit(1)
        predictions, references = load_jsonl_pairs(args.predictions, args.references)

    if args.max_samples:
        predictions = predictions[: args.max_samples]
        references = references[: args.max_samples]

    if not predictions:
        log.error("No predictions loaded")
        sys.exit(1)

    log.info("Evaluating %d samples …", len(predictions))
    results = evaluate(predictions, references)
    results_dict = results.as_dict()

    print("\n=== LexCorpus Evaluation Results ===")
    for k, v in results_dict.items():
        print(f"  {k:25s}: {v}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as fh:
            json.dump(results_dict, fh, indent=2, ensure_ascii=False)
        log.info("Results saved to %s", args.output)


if __name__ == "__main__":
    main()
