"""
self_rag_train.py — Fine-tune Bielik-7B/11B with Self-RAG reflection tokens.

Self-RAG (Asai et al., ICLR 2024) extends the LLM vocabulary with 4 special
reflection token types and trains the model to generate them during inference.
This allows the model to:
  - Decide when to retrieve (vs answer from parametric knowledge)
  - Judge relevance of retrieved passages
  - Assess whether a passage supports the generated answer
  - Self-score response utility

Training is identical to QLoRA SFT but requires:
1. Extended tokenizer vocabulary (add special tokens)
2. Self-RAG formatted data from self_rag_prepare.py
3. Standard causal LM loss over the entire sequence (including reflection tokens)

Usage:
    python training/self_rag_train.py \\
        --data data/dataset/self_rag/train.jsonl \\
        --model speakleash/Bielik-7B-Instruct-v0.1 \\
        --output output/bielik-self-rag \\
        --epochs 3

Requirements:
    pip install transformers peft bitsandbytes accelerate datasets
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

# Special tokens added to vocabulary
SELF_RAG_TOKENS = [
    "[Retrieve]", "[IsREL]", "[IsSUP]", "[IsUSE]",
    "[Passage]", "[/Passage]",
    # Value tokens
    "Tak", "Nie", "istotne", "nieistotne",
    "w pełni", "częściowo",
]

DEFAULT_MODEL = "speakleash/Bielik-7B-Instruct-v0.1"

LORA_CONFIG = {
    "r": 16,
    "lora_alpha": 32,
    "target_modules": ["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "lora_dropout": 0.05,
    "bias": "none",
    "task_type": "CAUSAL_LM",
}


def _load_dataset(data_path: Path, tokenizer, max_length: int = 2048, max_examples: int | None = None):
    """Load Self-RAG JSONL and tokenize using the model's chat template."""
    try:
        from datasets import Dataset
    except ImportError:
        log.error("datasets required: pip install datasets")
        sys.exit(1)

    records = []
    with data_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
            if max_examples and len(records) >= max_examples:
                break

    log.info("Loaded %d training examples", len(records))

    def tokenize(example):
        messages = example.get("messages", [])
        try:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        except Exception:
            # Fallback to manual format for Bielik instruction format
            text = ""
            for m in messages:
                if m["role"] == "user":
                    text += f"<s>[INST] {m['content']} [/INST] "
                elif m["role"] == "assistant":
                    text += f"{m['content']}</s>"

        encoded = tokenizer(
            text,
            max_length=max_length,
            truncation=True,
            padding=False,
            return_tensors=None,
        )
        encoded["labels"] = encoded["input_ids"].copy()
        return encoded

    dataset = Dataset.from_list(records)
    tokenized = dataset.map(tokenize, remove_columns=dataset.column_names, desc="Tokenizing")
    return tokenized


def train(
    data_path: Path,
    model_name: str,
    output_dir: str,
    num_epochs: int = 3,
    batch_size: int = 2,
    grad_accum: int = 8,
    learning_rate: float = 2e-4,
    max_length: int = 2048,
    max_examples: int | None = None,
    use_4bit: bool = True,
) -> None:
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForSeq2Seq,
            Trainer,
            TrainingArguments,
        )
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as e:
        log.error("Required packages missing: pip install transformers peft bitsandbytes accelerate: %s", e)
        sys.exit(1)

    log.info("Loading tokenizer from %s …", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Add Self-RAG special tokens to tokenizer vocabulary
    new_tokens = [t for t in SELF_RAG_TOKENS if t not in tokenizer.get_vocab()]
    if new_tokens:
        tokenizer.add_special_tokens({"additional_special_tokens": new_tokens})
        log.info("Added %d Self-RAG tokens to vocabulary: %s", len(new_tokens), new_tokens[:5])

    # Load model with optional 4-bit quantisation
    log.info("Loading model %s …", model_name)
    if use_4bit and torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto" if torch.cuda.is_available() else "cpu",
            trust_remote_code=True,
        )

    # Resize embeddings for new Self-RAG tokens
    model.resize_token_embeddings(len(tokenizer))

    # Apply LoRA
    lora_config = LoraConfig(**LORA_CONFIG)
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    log.info("Preparing dataset …")
    dataset = _load_dataset(data_path, tokenizer, max_length, max_examples)

    # 90/10 train/eval split
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_ds = split["train"]
    eval_ds = split["test"]

    collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True, pad_to_multiple_of=8)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        weight_decay=0.01,
        bf16=torch.cuda.is_available(),
        fp16=False,
        evaluation_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=200,
        save_total_limit=3,
        load_best_model_at_end=True,
        logging_steps=25,
        report_to="none",
        dataloader_num_workers=2,
        gradient_checkpointing=True,
        optim="paged_adamw_32bit" if use_4bit else "adamw_torch",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        tokenizer=tokenizer,
        data_collator=collator,
    )

    log.info("Starting Self-RAG fine-tuning …")
    trainer.train()

    # Save final merged model
    log.info("Saving model to %s …", output_dir)
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Merge LoRA weights into base model
    merged_dir = str(output_dir).rstrip("/") + "-merged"
    try:
        from peft import AutoPeftModelForCausalLM
        log.info("Merging LoRA weights into %s …", merged_dir)
        merged = AutoPeftModelForCausalLM.from_pretrained(
            output_dir, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True
        )
        merged = merged.merge_and_unload()
        merged.save_pretrained(merged_dir, safe_serialization=True)
        tokenizer.save_pretrained(merged_dir)
        log.info("Merged model saved to %s", merged_dir)
    except Exception as exc:
        log.warning("LoRA merge failed (non-critical): %s", exc)

    log.info(
        "Done. Self-RAG model at %s. Deploy with:\n"
        "  LOCAL_MODEL_PATH=%s in .env\n"
        "  or: docker compose -f docker-compose.yml -f docker-compose.vllm.yml up",
        output_dir, merged_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune Bielik with Self-RAG reflection tokens (QLoRA)."
    )
    parser.add_argument("--data", type=Path, default=Path("data/dataset/self_rag/train.jsonl"),
                        help="Self-RAG formatted JSONL from self_rag_prepare.py")
    parser.add_argument("--model", default=os.getenv("BASE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--output", type=Path, default=Path("output/bielik-self-rag"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--no-4bit", action="store_true", help="Disable 4-bit quantisation")
    args = parser.parse_args()

    if not args.data.exists():
        log.error("Training data not found: %s", args.data)
        log.error("Run: python training/self_rag_prepare.py --output %s", args.data)
        sys.exit(1)

    args.output.mkdir(parents=True, exist_ok=True)

    train(
        data_path=args.data,
        model_name=args.model,
        output_dir=str(args.output),
        num_epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        learning_rate=args.lr,
        max_length=args.max_length,
        max_examples=args.max_examples,
        use_4bit=not args.no_4bit,
    )


if __name__ == "__main__":
    main()
