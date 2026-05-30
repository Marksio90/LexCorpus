"""
quantize_bielik.py — AWQ / GGUF / GPTQ quantization for Bielik-11B-v2.3-Instruct.

From research: AWQ + Marlin kernel achieves ~741 tok/s for 7B models at ~95% quality
retention.  For Bielik-11B, AWQ is the production choice on NVIDIA GPUs; GGUF is the
preferred format for CPU / dev machines (llama.cpp).

Supported methods
-----------------
  awq   — autoawq library, calibrated on domain-specific Polish legal text
  gguf  — converts any HuggingFace model via llama.cpp convert_hf_to_gguf.py
  gptq  — auto-gptq library (kept for completeness; AWQ preferred for Marlin)

CLI
---
    python scripts/quantize_bielik.py \\
        --method awq \\
        --model speakleash/Bielik-11B-v2.3-Instruct \\
        --output output/bielik-awq \\
        --calibration data/processed/chunks.jsonl

    python scripts/quantize_bielik.py \\
        --method gguf \\
        --model output/bielik-awq \\
        --output output/bielik-gguf \\
        --gguf-quant Q4_K_M

    python scripts/quantize_bielik.py \\
        --method benchmark \\
        --model output/bielik-awq
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

SUPPORTED_METHODS = ["awq", "gguf", "gptq", "benchmark"]

# Polish legal system prompt used for benchmark prompts
_LEGAL_SYSTEM = (
    "Jesteś ekspertem ds. polskiego prawa. Odpowiadasz zwięźle i precyzyjnie."
)

_BENCHMARK_PROMPTS: list[str] = [
    "Jakie są podstawowe prawa pracownika wynikające z Kodeksu pracy?",
    "Kiedy pracodawca może wypowiedzieć umowę o pracę bez wypowiedzenia?",
    "Co to jest hipoteka i jak jest ustanawiana?",
    "Jakie dokumenty są wymagane do zawarcia umowy kupna-sprzedaży nieruchomości?",
    "Kiedy obywatel może wnieść skargę konstytucyjną do Trybunału Konstytucyjnego?",
    "Jakie są terminy przedawnienia roszczeń majątkowych w prawie cywilnym?",
    "Co to jest spółka z ograniczoną odpowiedzialnością i jakie są jej główne cechy?",
    "Jakie obowiązki ma podatnik prowadzący działalność gospodarczą?",
]


# ---------------------------------------------------------------------------
# Calibration data
# ---------------------------------------------------------------------------


def load_calibration_texts(
    calibration_path: str,
    max_samples: int = 512,
    min_length: int = 100,
) -> list[str]:
    """Load Polish legal texts from chunks.jsonl for domain-specific calibration.

    Using domain-specific calibration (ISAP / SAOS) instead of generic datasets
    preserves legal vocabulary and improves quality retention on downstream tasks.
    """
    path = Path(calibration_path)
    texts: list[str] = []

    if not path.exists():
        log.warning(
            "Calibration file not found: %s — falling back to generic calibration",
            path,
        )
        return texts

    log.info("Loading calibration texts from %s …", path)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = rec.get("text", "")
            if len(text) < min_length:
                continue

            # Include title + text for richer context
            title = rec.get("title", "")
            full = f"{title}\n\n{text}".strip() if title else text
            texts.append(full[:2048])  # cap per-sample length

            if len(texts) >= max_samples:
                break

    log.info("Loaded %d calibration samples", len(texts))
    return texts


# ---------------------------------------------------------------------------
# AWQ quantization
# ---------------------------------------------------------------------------


def quantize_awq(
    model_name: str = "speakleash/Bielik-11B-v2.3-Instruct",
    output_dir: str = "output/bielik-11b-awq",
    bits: int = 4,
    group_size: int = 128,
    calibration_dataset: str = "data/processed/chunks.jsonl",
    max_calib_samples: int = 512,
    zero_point: bool = True,
    version: str = "GEMM",
) -> Path:
    """AWQ quantization using the autoawq library.

    Uses ISAP/SAOS chunks as calibration data for better quality on Polish legal text.
    The 'GEMM' version is Marlin-compatible (fast on NVIDIA Ampere/Ada GPUs).

    Parameters
    ----------
    model_name:
        HuggingFace model id or local path.
    output_dir:
        Where to save the quantized model.
    bits:
        Quantization bits (4 is standard for AWQ).
    group_size:
        Weight group size; 128 is the standard AWQ value.
    calibration_dataset:
        Path to chunks.jsonl for domain calibration.
    max_calib_samples:
        Number of calibration samples (more = slower but better).
    zero_point:
        Whether to use zero-point quantization (improves quality slightly).
    version:
        'GEMM' (Marlin-compatible, faster inference) or 'GEMV' (memory-saving).

    Returns
    -------
    Path to the saved quantized model directory.
    """
    try:
        from awq import AutoAWQForCausalLM
        from transformers import AutoTokenizer
    except ImportError as exc:
        log.error(
            "autoawq not installed. Run: pip install autoawq\n"
            "See https://github.com/casper-hansen/AutoAWQ for CUDA requirements.\n"
            "Error: %s",
            exc,
        )
        sys.exit(1)

    _check_cuda_or_warn("AWQ")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    quant_config = {
        "zero_point": zero_point,
        "q_group_size": group_size,
        "w_bit": bits,
        "version": version,
    }
    log.info(
        "AWQ quantization | model=%s bits=%d group_size=%d version=%s",
        model_name, bits, group_size, version,
    )
    log.info("Quantization config: %s", quant_config)

    log.info("Loading model for quantization …")
    model = AutoAWQForCausalLM.from_pretrained(
        model_name,
        low_cpu_mem_usage=True,
        use_cache=False,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Build calibration dataset
    calib_texts = load_calibration_texts(calibration_dataset, max_calib_samples)
    if not calib_texts:
        log.warning("No domain calibration data — using default autoawq calibration")
        calib_data = None
    else:
        # autoawq accepts a list of strings directly when passed as calib_data
        calib_data = calib_texts

    log.info(
        "Starting AWQ quantization with %d calibration samples …",
        len(calib_data) if calib_data else 0,
    )
    t0 = time.time()

    try:
        if calib_data:
            model.quantize(tokenizer, quant_config=quant_config, calib_data=calib_data)
        else:
            model.quantize(tokenizer, quant_config=quant_config)
    except TypeError:
        # Older autoawq versions use positional calib_data
        log.warning("autoawq API mismatch — retrying without calib_data keyword")
        model.quantize(tokenizer, quant_config=quant_config)

    elapsed = time.time() - t0
    log.info("AWQ quantization complete in %.0f s", elapsed)

    # Save quantized model and tokenizer
    log.info("Saving quantized model to %s …", out_path)
    model.save_quantized(str(out_path))
    tokenizer.save_pretrained(str(out_path))

    # Write a metadata file for reproducibility
    meta = {
        "source_model": model_name,
        "method": "awq",
        "bits": bits,
        "group_size": group_size,
        "version": version,
        "zero_point": zero_point,
        "calib_samples": len(calib_data) if calib_data else 0,
        "calib_path": str(calibration_dataset),
        "quantization_time_s": round(elapsed, 1),
    }
    (out_path / "quantization_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    log.info("AWQ model saved to: %s", out_path)
    log.info(
        "Load with: AutoAWQForCausalLM.from_quantized('%s', fuse_layers=True)",
        out_path,
    )
    return out_path


# ---------------------------------------------------------------------------
# GGUF conversion
# ---------------------------------------------------------------------------


def quantize_gguf(
    model_name_or_path: str,
    output_dir: str = "output/bielik-11b-gguf",
    quantization: str = "Q4_K_M",
    llama_cpp_dir: Optional[str] = None,
) -> Path:
    """Convert a HuggingFace model to GGUF format using llama.cpp.

    GGUF is the standard format for llama.cpp, Ollama, and LM Studio.
    Q4_K_M gives the best quality/size tradeoff (~4.8 GB for 7B, ~10 GB for 13B).

    Common quantization types:
        Q4_K_M  — best quality/size (recommended default)
        Q5_K_M  — higher quality, ~20% larger
        Q8_0    — near-lossless, 2x size of Q4_K_M
        Q2_K    — smallest, significant quality loss
        f16     — full half-precision, no quality loss

    Parameters
    ----------
    model_name_or_path:
        HuggingFace model id or local path. If HuggingFace id, the model is
        first downloaded with snapshot_download.
    output_dir:
        Where to save the .gguf file.
    quantization:
        GGUF quantization type (see llama.cpp README for full list).
    llama_cpp_dir:
        Path to a cloned llama.cpp repository. If None, the script tries to
        find it via LLAMA_CPP_DIR env var, then common locations.

    Returns
    -------
    Path to the saved .gguf file.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Resolve llama.cpp directory
    cpp_dir = _find_llama_cpp(llama_cpp_dir)
    if cpp_dir is None:
        log.error(
            "llama.cpp not found. Options:\n"
            "  1. Set --llama-cpp-dir /path/to/llama.cpp\n"
            "  2. Set LLAMA_CPP_DIR env var\n"
            "  3. Clone: git clone https://github.com/ggerganov/llama.cpp\n"
            "     and build: cd llama.cpp && cmake -B build && cmake --build build -j"
        )
        sys.exit(1)

    # Resolve local model path (download if HuggingFace id)
    local_model_path = _resolve_model_path(model_name_or_path)

    # Step 1: Convert HuggingFace → GGUF (fp16 intermediate)
    model_slug = Path(model_name_or_path).name.replace("/", "_")
    fp16_gguf = out_path / f"{model_slug}-f16.gguf"
    convert_script = cpp_dir / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        # Try older name
        convert_script = cpp_dir / "convert.py"
    if not convert_script.exists():
        log.error("convert_hf_to_gguf.py not found in %s", cpp_dir)
        sys.exit(1)

    log.info("Step 1/2: Converting %s → %s (fp16) …", local_model_path, fp16_gguf)
    cmd_convert = [
        sys.executable, str(convert_script),
        str(local_model_path),
        "--outfile", str(fp16_gguf),
        "--outtype", "f16",
    ]
    log.info("Running: %s", " ".join(cmd_convert))
    result = subprocess.run(cmd_convert, capture_output=False, text=True)
    if result.returncode != 0:
        log.error("Conversion failed with exit code %d", result.returncode)
        sys.exit(result.returncode)

    # Step 2: Quantize fp16 GGUF → target quantization
    final_gguf = out_path / f"{model_slug}-{quantization}.gguf"
    quantize_bin = _find_llama_quantize_binary(cpp_dir)
    if quantize_bin is None:
        log.error(
            "llama-quantize binary not found. Build llama.cpp first:\n"
            "  cd %s && cmake -B build && cmake --build build -j",
            cpp_dir,
        )
        sys.exit(1)

    log.info(
        "Step 2/2: Quantizing %s → %s (%s) …",
        fp16_gguf, final_gguf, quantization,
    )
    cmd_quant = [str(quantize_bin), str(fp16_gguf), str(final_gguf), quantization]
    log.info("Running: %s", " ".join(cmd_quant))
    result = subprocess.run(cmd_quant, capture_output=False, text=True)
    if result.returncode != 0:
        log.error("Quantization failed with exit code %d", result.returncode)
        sys.exit(result.returncode)

    # Clean up fp16 intermediate if final file was created
    if final_gguf.exists() and fp16_gguf.exists():
        log.info("Removing fp16 intermediate: %s", fp16_gguf)
        fp16_gguf.unlink()

    log.info("GGUF model saved to: %s", final_gguf)
    log.info("Run with: ollama create bielik -f Modelfile  (point to %s)", final_gguf)
    return final_gguf


# ---------------------------------------------------------------------------
# GPTQ quantization
# ---------------------------------------------------------------------------


def quantize_gptq(
    model_name: str = "speakleash/Bielik-11B-v2.3-Instruct",
    output_dir: str = "output/bielik-11b-gptq",
    bits: int = 4,
    group_size: int = 128,
    calibration_dataset: str = "data/processed/chunks.jsonl",
    max_calib_samples: int = 128,
    desc_act: bool = False,
) -> Path:
    """GPTQ quantization using auto-gptq.

    Note: AWQ is preferred over GPTQ for most use cases because AWQ:
      - Is faster to quantize (~10x less calibration passes)
      - Has better Marlin kernel support
      - Shows equal or better perplexity at same bit-width
    GPTQ is included here for compatibility with vLLM and environments that
    do not yet support AWQ.

    Parameters
    ----------
    desc_act:
        Activation ordering (True = better quality, slower quantization).
    """
    try:
        from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
        from transformers import AutoTokenizer
    except ImportError as exc:
        log.error(
            "auto-gptq not installed. Run: pip install auto-gptq\n"
            "Error: %s",
            exc,
        )
        sys.exit(1)

    _check_cuda_or_warn("GPTQ")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    log.info(
        "GPTQ quantization | model=%s bits=%d group_size=%d desc_act=%s",
        model_name, bits, group_size, desc_act,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    calib_texts = load_calibration_texts(calibration_dataset, max_calib_samples)
    if not calib_texts:
        log.warning("No calibration data; using empty dataset (quality will be reduced)")
        calib_texts = [""]

    # Tokenize calibration data
    calib_data = [
        tokenizer(t, return_tensors="pt", truncation=True, max_length=2048)
        for t in calib_texts
    ]

    quantize_config = BaseQuantizeConfig(
        bits=bits,
        group_size=group_size,
        desc_act=desc_act,
    )

    log.info("Loading model …")
    model = AutoGPTQForCausalLM.from_pretrained(
        model_name,
        quantize_config=quantize_config,
        trust_remote_code=True,
    )

    log.info("Running GPTQ quantization on %d samples …", len(calib_data))
    t0 = time.time()
    model.quantize(calib_data)
    elapsed = time.time() - t0
    log.info("GPTQ quantization complete in %.0f s", elapsed)

    log.info("Saving to %s …", out_path)
    model.save_quantized(str(out_path), use_safetensors=True)
    tokenizer.save_pretrained(str(out_path))

    meta = {
        "source_model": model_name,
        "method": "gptq",
        "bits": bits,
        "group_size": group_size,
        "desc_act": desc_act,
        "calib_samples": len(calib_data),
        "quantization_time_s": round(elapsed, 1),
    }
    (out_path / "quantization_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    log.info("GPTQ model saved to: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


def benchmark_model(
    model_path: str,
    test_prompts: Optional[list[str]] = None,
    max_new_tokens: int = 128,
    device: str = "auto",
) -> dict:
    """Measure inference speed (tokens/sec) and perplexity on Polish legal text.

    Parameters
    ----------
    model_path:
        Path to a HuggingFace-compatible model (standard, AWQ, GPTQ).
    test_prompts:
        List of prompts to run. Defaults to built-in Polish legal prompts.
    max_new_tokens:
        Tokens to generate per prompt for throughput measurement.
    device:
        'cuda', 'cpu', or 'auto'.

    Returns
    -------
    Dict with keys: tokens_per_second, perplexity, latency_p50_ms, latency_p95_ms,
    model_size_gb, gpu_memory_gb, total_prompts, total_tokens.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if test_prompts is None:
        test_prompts = _BENCHMARK_PROMPTS

    log.info("Benchmarking model: %s", model_path)
    log.info("Loading model and tokenizer …")

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    load_kwargs: dict = {"trust_remote_code": True}
    if device == "auto":
        load_kwargs["device_map"] = "auto"
        if torch.cuda.is_available():
            load_kwargs["torch_dtype"] = torch.float16
        else:
            load_kwargs["torch_dtype"] = torch.float32

    t_load = time.time()
    model = AutoModelForCausalLM.from_pretrained(model_path, **load_kwargs)
    model.eval()
    load_time = time.time() - t_load
    log.info("Model loaded in %.1f s", load_time)

    # GPU memory usage
    gpu_mem_gb = 0.0
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        gpu_mem_gb = round(
            torch.cuda.max_memory_allocated() / 1024 ** 3, 2
        )

    # Model parameter size estimate
    n_params = sum(p.numel() for p in model.parameters())
    model_size_gb = round(n_params * 2 / 1024 ** 3, 2)  # fp16 estimate

    # Throughput benchmark
    latencies_ms: list[float] = []
    total_tokens_generated = 0

    log.info("Running throughput benchmark on %d prompts …", len(test_prompts))
    for i, prompt in enumerate(test_prompts):
        messages = [
            {"role": "system", "content": _LEGAL_SYSTEM},
            {"role": "user",   "content": prompt},
        ]
        if hasattr(tokenizer, "apply_chat_template"):
            formatted = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            formatted = f"### System:\n{_LEGAL_SYSTEM}\n\n### User:\n{prompt}\n\n### Assistant:\n"

        inputs = tokenizer(formatted, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        t0 = time.perf_counter()
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=tokenizer.eos_token_id,
            )
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        n_new = output_ids.shape[-1] - inputs["input_ids"].shape[-1]
        total_tokens_generated += n_new
        latencies_ms.append(elapsed_ms)
        log.info(
            "  [%d/%d] %d tokens in %.0f ms (%.1f tok/s)",
            i + 1, len(test_prompts), n_new, elapsed_ms,
            n_new / (elapsed_ms / 1000) if elapsed_ms > 0 else 0,
        )

    latencies_ms.sort()
    total_time_s = sum(latencies_ms) / 1000
    tok_per_sec = total_tokens_generated / total_time_s if total_time_s > 0 else 0.0
    n = len(latencies_ms)
    p50 = latencies_ms[n // 2] if n else 0.0
    p95 = latencies_ms[int(n * 0.95)] if n else 0.0

    # Perplexity on a held-out legal text (approx, using a fixed sample)
    ppl = _compute_perplexity(model, tokenizer)

    results = {
        "model_path": str(model_path),
        "tokens_per_second": round(tok_per_sec, 1),
        "perplexity": round(ppl, 3),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "model_size_gb_fp16_estimate": model_size_gb,
        "gpu_memory_gb": gpu_mem_gb,
        "total_prompts": len(test_prompts),
        "total_tokens_generated": total_tokens_generated,
        "load_time_s": round(load_time, 1),
    }

    log.info("=== Benchmark results ===")
    for k, v in results.items():
        log.info("  %-35s %s", k + ":", v)

    return results


def _compute_perplexity(model, tokenizer, max_length: int = 512) -> float:
    """Compute approximate perplexity on a short fixed Polish legal text."""
    sample = (
        "Art. 22. § 1. Przez nawiązanie stosunku pracy pracownik zobowiązuje się "
        "do wykonywania pracy określonego rodzaju na rzecz pracodawcy i pod jego "
        "kierownictwem oraz w miejscu i czasie wyznaczonym przez pracodawcę, "
        "a pracodawca — do zatrudniania pracownika za wynagrodzeniem. "
        "§ 2. Zatrudnienie w warunkach określonych w § 1 jest zatrudnieniem na podstawie "
        "stosunku pracy, bez względu na nazwę zawartej przez strony umowy."
    )
    encodings = tokenizer(sample, return_tensors="pt", truncation=True, max_length=max_length)
    if torch.cuda.is_available():
        encodings = {k: v.cuda() for k, v in encodings.items()}

    import math
    try:
        with torch.no_grad():
            outputs = model(**encodings, labels=encodings["input_ids"])
            ppl = math.exp(outputs.loss.item())
    except Exception as exc:
        log.warning("Perplexity computation failed: %s", exc)
        ppl = float("nan")
    return ppl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_cuda_or_warn(method: str) -> None:
    """Warn if CUDA is not available (AWQ and GPTQ require GPU)."""
    if not torch.cuda.is_available():
        log.warning(
            "CUDA not available! %s quantization requires a CUDA GPU.\n"
            "  - For CPU-based quantization use GGUF (--method gguf).\n"
            "  - On this machine torch.cuda.is_available() = False.",
            method,
        )
    else:
        n = torch.cuda.device_count()
        for i in range(n):
            props = torch.cuda.get_device_properties(i)
            mem_gb = props.total_memory / 1024 ** 3
            log.info(
                "GPU %d: %s (%.1f GB VRAM, compute capability %d.%d)",
                i, props.name, mem_gb, props.major, props.minor,
            )
        if n == 0:
            log.warning("No CUDA devices detected.")


def _find_llama_cpp(hint: Optional[str]) -> Optional[Path]:
    """Search for llama.cpp directory from hint, env var, or common locations."""
    candidates = []
    if hint:
        candidates.append(Path(hint))
    env_hint = os.getenv("LLAMA_CPP_DIR")
    if env_hint:
        candidates.append(Path(env_hint))
    # Common relative/absolute locations
    for loc in ["./llama.cpp", "../llama.cpp", os.path.expanduser("~/llama.cpp")]:
        candidates.append(Path(loc))

    for candidate in candidates:
        if candidate.is_dir() and (
            (candidate / "convert_hf_to_gguf.py").exists()
            or (candidate / "convert.py").exists()
        ):
            log.info("Found llama.cpp at: %s", candidate)
            return candidate.resolve()
    return None


def _find_llama_quantize_binary(cpp_dir: Path) -> Optional[Path]:
    """Find the llama-quantize binary inside a llama.cpp build directory."""
    candidates = [
        cpp_dir / "build" / "bin" / "llama-quantize",
        cpp_dir / "build" / "llama-quantize",
        cpp_dir / "quantize",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _resolve_model_path(model_name_or_path: str) -> Path:
    """If model is a local path, return it. Otherwise, download via HuggingFace."""
    local = Path(model_name_or_path)
    if local.exists():
        return local.resolve()

    # Download from HuggingFace Hub
    log.info("Downloading model from HuggingFace Hub: %s …", model_name_or_path)
    try:
        from huggingface_hub import snapshot_download
        local_dir = snapshot_download(model_name_or_path)
        return Path(local_dir)
    except ImportError:
        log.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        sys.exit(1)
    except Exception as exc:
        log.error("Model download failed: %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quantize Bielik-11B to AWQ / GGUF / GPTQ.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--method",
        choices=SUPPORTED_METHODS,
        required=True,
        help="Quantization method (awq | gguf | gptq | benchmark)",
    )
    parser.add_argument(
        "--model",
        default="speakleash/Bielik-11B-v2.3-Instruct",
        help="HuggingFace model id or local path",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (defaults per method)",
    )
    parser.add_argument(
        "--calibration",
        default="data/processed/chunks.jsonl",
        help="Path to chunks.jsonl for calibration (AWQ / GPTQ)",
    )
    parser.add_argument(
        "--bits",
        type=int,
        default=4,
        help="Quantization bits (AWQ / GPTQ)",
    )
    parser.add_argument(
        "--group-size",
        type=int,
        default=128,
        help="Weight group size (AWQ / GPTQ)",
    )
    parser.add_argument(
        "--max-calib-samples",
        type=int,
        default=512,
        help="Max calibration samples (AWQ / GPTQ)",
    )
    parser.add_argument(
        "--gguf-quant",
        default="Q4_K_M",
        help="GGUF quantization type (e.g. Q4_K_M, Q5_K_M, Q8_0)",
    )
    parser.add_argument(
        "--llama-cpp-dir",
        default=None,
        help="Path to cloned llama.cpp repository (for GGUF)",
    )
    parser.add_argument(
        "--awq-version",
        default="GEMM",
        choices=["GEMM", "GEMV"],
        help="AWQ kernel version: GEMM (Marlin-compatible) or GEMV",
    )
    parser.add_argument(
        "--benchmark-only",
        action="store_true",
        help="Run benchmark only (skip quantization)",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=128,
        help="Max tokens per prompt in benchmark",
    )

    args = parser.parse_args()

    if args.method == "awq":
        out = args.output or "output/bielik-11b-awq"
        quantize_awq(
            model_name=args.model,
            output_dir=out,
            bits=args.bits,
            group_size=args.group_size,
            calibration_dataset=args.calibration,
            max_calib_samples=args.max_calib_samples,
            version=args.awq_version,
        )

    elif args.method == "gguf":
        out = args.output or "output/bielik-11b-gguf"
        quantize_gguf(
            model_name_or_path=args.model,
            output_dir=out,
            quantization=args.gguf_quant,
            llama_cpp_dir=args.llama_cpp_dir,
        )

    elif args.method == "gptq":
        out = args.output or "output/bielik-11b-gptq"
        quantize_gptq(
            model_name=args.model,
            output_dir=out,
            bits=args.bits,
            group_size=args.group_size,
            calibration_dataset=args.calibration,
            max_calib_samples=args.max_calib_samples,
        )

    elif args.method == "benchmark":
        results = benchmark_model(
            model_path=args.model,
            max_new_tokens=args.max_new_tokens,
        )
        out_path = Path(args.output or "output") / "benchmark_results.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("Benchmark results saved to: %s", out_path)


if __name__ == "__main__":
    main()
