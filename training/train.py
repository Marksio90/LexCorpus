"""
train.py — QLoRA fine-tuning of Bielik-7B-Instruct on Polish legal data.

Uses PEFT (LoRA) + bitsandbytes 4-bit quantization + HuggingFace Trainer.
Configuration is loaded from training/config.yaml.

Usage:
    python training/train.py
    python training/train.py --config training/config.yaml
    python training/train.py --config training/config.yaml --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch
import yaml
from datasets import DatasetDict, load_from_disk
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
    set_seed,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DEFAULT_CONFIG = Path(__file__).parent / "config.yaml"


def load_config(path: Path) -> dict:
    """Load YAML training config."""
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_bnb_config(cfg: dict) -> BitsAndBytesConfig:
    """Build BitsAndBytesConfig for 4-bit quantization."""
    q = cfg["quantization"]
    dtype_map = {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}
    compute_dtype = dtype_map.get(q["bnb_4bit_compute_dtype"], torch.float16)

    return BitsAndBytesConfig(
        load_in_4bit=q["load_in_4bit"],
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_quant_type=q["bnb_4bit_quant_type"],
        bnb_4bit_use_double_quant=q["bnb_4bit_use_double_quant"],
    )


def load_model_and_tokenizer(cfg: dict, bnb_config: BitsAndBytesConfig) -> tuple:
    """Load base model with 4-bit quantization and tokenizer."""
    model_id = cfg["model"]["base_model_id"]

    log.info("Loading tokenizer from %s …", model_id)
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        trust_remote_code=cfg["model"]["trust_remote_code"],
        padding_side="right",  # required for causal LM training
    )
    # Ensure pad token exists
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    log.info("Loading model from %s with 4-bit quantization …", model_id)
    try:
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=cfg["model"]["trust_remote_code"],
        )
    except OSError:
        # Fallback to alternative model if primary not available
        fallback = cfg["model"]["fallback_model_id"]
        log.warning("Primary model not available, falling back to %s", fallback)
        model = AutoModelForCausalLM.from_pretrained(
            fallback,
            quantization_config=bnb_config,
            device_map="auto",
        )
        tokenizer = AutoTokenizer.from_pretrained(fallback, padding_side="right")
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id

    return model, tokenizer


def apply_lora(model, cfg: dict):
    """Wrap model with LoRA adapters using PEFT."""
    lora_cfg = cfg["lora"]

    # Prepare model for k-bit (4-bit) training
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=cfg["training"]["gradient_checkpointing"],
    )

    lora_config = LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        lora_dropout=lora_cfg["lora_dropout"],
        bias=lora_cfg["bias"],
        task_type=TaskType.CAUSAL_LM,
        target_modules=lora_cfg["target_modules"],
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


def format_prompt(example: dict, template: str) -> str:
    """Format an instruction-tuning record into a single prompt string."""
    return template.format(
        instruction=example.get("instruction", ""),
        input=example.get("input", ""),
        output=example.get("output", ""),
    )


def tokenize_dataset(dataset: DatasetDict, tokenizer, cfg: dict) -> DatasetDict:
    """Tokenize all splits of the dataset."""
    max_seq_len = cfg["training"]["max_seq_length"]
    template = cfg["data"]["prompt_template"]

    def tokenize_fn(examples):
        # Format each example into a full prompt
        texts = [
            format_prompt(
                {
                    "instruction": instr,
                    "input": inp,
                    "output": out,
                },
                template,
            )
            for instr, inp, out in zip(
                examples["instruction"],
                examples["input"],
                examples["output"],
            )
        ]

        tokenized = tokenizer(
            texts,
            truncation=True,
            max_length=max_seq_len,
            padding=False,
            return_tensors=None,
        )
        # For causal LM, labels = input_ids (shifted inside the model)
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized

    log.info("Tokenizing dataset …")
    tokenized = dataset.map(
        tokenize_fn,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenizing",
    )
    return tokenized


def build_training_args(cfg: dict) -> TrainingArguments:
    """Construct HuggingFace TrainingArguments from config dict."""
    t = cfg["training"]
    return TrainingArguments(
        output_dir=t["output_dir"],
        num_train_epochs=t["num_train_epochs"],
        per_device_train_batch_size=t["per_device_train_batch_size"],
        per_device_eval_batch_size=t["per_device_eval_batch_size"],
        gradient_accumulation_steps=t["gradient_accumulation_steps"],
        gradient_checkpointing=t["gradient_checkpointing"],
        optim=t["optim"],
        learning_rate=t["learning_rate"],
        weight_decay=t["weight_decay"],
        lr_scheduler_type=t["lr_scheduler_type"],
        warmup_ratio=t["warmup_ratio"],
        fp16=t["fp16"],
        bf16=t["bf16"],
        logging_steps=t["logging_steps"],
        eval_strategy=t["eval_strategy"],
        eval_steps=t["eval_steps"],
        save_strategy=t["save_strategy"],
        save_steps=t["save_steps"],
        save_total_limit=t["save_total_limit"],
        load_best_model_at_end=t["load_best_model_at_end"],
        metric_for_best_model=t["metric_for_best_model"],
        greater_is_better=t["greater_is_better"],
        report_to=t["report_to"],
        dataloader_num_workers=t["dataloader_num_workers"],
        remove_unused_columns=t["remove_unused_columns"],
        group_by_length=t["group_by_length"],
    )


def merge_and_save(model, tokenizer, cfg: dict) -> None:
    """Merge LoRA weights into the base model and save."""
    from peft import PeftModel

    merged_dir = cfg["merge"]["merged_output_dir"]
    log.info("Merging LoRA weights into base model …")
    merged_model = model.merge_and_unload()
    log.info("Saving merged model to %s …", merged_dir)
    merged_model.save_pretrained(merged_dir, safe_serialization=True)
    tokenizer.save_pretrained(merged_dir)
    log.info("Merged model saved successfully")


def main() -> None:
    parser = argparse.ArgumentParser(description="QLoRA fine-tuning for LexCorpus.")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to training config YAML",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load model and dataset but skip actual training (for debugging)",
    )
    args = parser.parse_args()

    if not args.config.exists():
        log.error("Config file not found: %s", args.config)
        sys.exit(1)

    cfg = load_config(args.config)
    set_seed(42)

    log.info("=== LexCorpus QLoRA Training ===")
    log.info("Base model: %s", cfg["model"]["base_model_id"])
    log.info("LoRA r=%d, alpha=%d", cfg["lora"]["r"], cfg["lora"]["lora_alpha"])

    # Load dataset
    dataset_path = cfg["data"]["dataset_path"]
    log.info("Loading dataset from %s …", dataset_path)
    dataset = load_from_disk(dataset_path)

    # Subsample if configured
    max_train = cfg["data"].get("max_samples_train")
    max_eval = cfg["data"].get("max_samples_eval")
    if max_train and max_train < len(dataset["train"]):
        dataset["train"] = dataset["train"].select(range(max_train))
        log.info("Subsampled train to %d examples", max_train)
    if max_eval and "validation" in dataset and max_eval < len(dataset["validation"]):
        dataset["validation"] = dataset["validation"].select(range(max_eval))
        log.info("Subsampled validation to %d examples", max_eval)

    if args.dry_run:
        log.info("Dry run: verifying dataset columns: %s", dataset["train"].column_names)

    # Build quantization config and load model
    bnb_config = build_bnb_config(cfg)
    model, tokenizer = load_model_and_tokenizer(cfg, bnb_config)

    # Apply LoRA
    model = apply_lora(model, cfg)

    # Tokenize
    tokenized_dataset = tokenize_dataset(dataset, tokenizer, cfg)

    if args.dry_run:
        log.info("Dry run complete. Model and dataset loaded successfully.")
        log.info("Train size: %d, Val size: %d", len(tokenized_dataset["train"]), len(tokenized_dataset.get("validation", [])))
        return

    # Build trainer
    training_args = build_training_args(cfg)
    data_collator = DataCollatorForSeq2Seq(
        tokenizer,
        model=model,
        label_pad_token_id=-100,
        pad_to_multiple_of=8,
    )

    eval_dataset = tokenized_dataset.get("validation", None)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )

    log.info("Starting training …")
    trainer.train()
    log.info("Training complete.")

    # Save the LoRA adapter
    lora_output = cfg["training"]["output_dir"]
    log.info("Saving LoRA adapter to %s …", lora_output)
    trainer.model.save_pretrained(lora_output)
    tokenizer.save_pretrained(lora_output)

    # Optionally merge into base model
    if cfg.get("merge", {}).get("merge_and_save", False):
        merge_and_save(trainer.model, tokenizer, cfg)

    log.info("All done.")


if __name__ == "__main__":
    main()
