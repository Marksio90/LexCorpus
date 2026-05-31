"""
llm_providers.py — LLM backend abstraction layer.

Decouples LLM generation logic from routing and retrieval code.
Supports three backends:
  OpenAIProvider            — real OpenAI API (GPT-4o-mini, GPT-4o, …)
  VLLMProvider              — vLLM local inference server (OpenAI-compatible)
  LocalTransformersProvider — HuggingFace Transformers (direct GPU inference)

A FallbackProvider chains multiple backends: if the primary fails, the next
in the list is tried automatically.

Usage:
    provider = build_provider()
    answer, model_id = provider.generate([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ])

    for delta in provider.stream(messages):
        print(delta, end="", flush=True)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterator

log = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract LLM backend — all implementations expose generate() and stream()."""

    @abstractmethod
    def generate(self, messages: list[dict], max_tokens: int = 1024) -> tuple[str, str]:
        """
        Generate a full response synchronously.

        Args:
            messages: OpenAI-format message list [{"role": ..., "content": ...}, …]
            max_tokens: Maximum number of tokens to generate.

        Returns:
            (answer_text, model_identifier)
        """

    @abstractmethod
    def stream(self, messages: list[dict], max_tokens: int = 1500) -> Iterator[str]:
        """
        Stream response — yields text deltas one by one.

        Args:
            messages: OpenAI-format message list.
            max_tokens: Maximum tokens to generate.

        Yields:
            String text fragments (tokens or short chunks).
        """

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Human-readable model identifier for API responses."""


class OpenAIProvider(LLMProvider):
    """OpenAI API backend (GPT-4o-mini, GPT-4o, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: float = 90.0) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    @property
    def model_id(self) -> str:
        return self._model

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> tuple[str, str]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip(), self._model

    def stream(self, messages: list[dict], max_tokens: int = 1500) -> Iterator[str]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class VLLMProvider(LLMProvider):
    """
    vLLM local inference server (OpenAI-compatible REST API).

    vLLM exposes the same /v1/chat/completions endpoint as OpenAI, so the
    standard openai library works with a custom base_url.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        from openai import OpenAI
        # vLLM doesn't require a real key but the SDK requires a non-empty value
        self._client = OpenAI(base_url=base_url, api_key="vllm-no-auth", timeout=timeout)
        self._model = model
        self._base_url = base_url

    @property
    def model_id(self) -> str:
        return f"vllm:{self._model}"

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> tuple[str, str]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip(), self.model_id

    def stream(self, messages: list[dict], max_tokens: int = 1500) -> Iterator[str]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class LocalTransformersProvider(LLMProvider):
    """
    Local HuggingFace Transformers model loaded directly via GPU.

    Streaming: token-level streaming isn't implemented — stream() yields the
    full response in a single chunk. This is transparent to callers (they
    still iterate over the generator), but the user won't see progressive output.
    """

    def __init__(self, model_path: str, is_bielik: bool = False) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        log.info("Loading local model from %s …", model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        self._model.eval()
        self._model_path = model_path
        self._is_bielik = is_bielik
        log.info("Local model loaded (%s)", model_path)

    @property
    def model_id(self) -> str:
        return self._model_path

    def _build_prompt(self, messages: list[dict]) -> str:
        if self._is_bielik and hasattr(self._tokenizer, "apply_chat_template"):
            try:
                return self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            except Exception:
                pass
        # Generic fallback format compatible with Bielik instruction style
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"### Instrukcja:\n{content}")
            elif role == "user":
                parts.append(f"### Pytanie:\n{content}")
            elif role == "assistant":
                parts.append(f"### Odpowiedź:\n{content}")
        return "\n\n".join(parts) + "\n\n### Odpowiedź:\n"

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> tuple[str, str]:
        import torch
        full_prompt = self._build_prompt(messages)
        inputs = self._tokenizer(
            full_prompt, return_tensors="pt", truncation=True, max_length=4096
        )
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=0.3,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        generated = output_ids[0][inputs["input_ids"].shape[1]:]
        return self._tokenizer.decode(generated, skip_special_tokens=True).strip(), self._model_path

    def stream(self, messages: list[dict], max_tokens: int = 1500) -> Iterator[str]:
        # Local model doesn't support true token streaming — yield full answer as one chunk.
        answer, _ = self.generate(messages, max_tokens=max_tokens)
        yield answer


class FallbackProvider(LLMProvider):
    """
    Chain of providers tried in order — if the primary fails, the next is used.

    model_id reports the first provider's identifier; generate/stream return the
    model_id of whichever provider actually succeeded.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider requires at least one provider")
        self._providers = providers

    @property
    def model_id(self) -> str:
        return self._providers[0].model_id

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> tuple[str, str]:
        last_exc: Exception | None = None
        for provider in self._providers:
            try:
                return provider.generate(messages, max_tokens)
            except Exception as exc:
                log.warning("Provider '%s' failed, trying next: %s", provider.model_id, exc)
                last_exc = exc
        raise RuntimeError("All LLM providers failed") from last_exc

    def stream(self, messages: list[dict], max_tokens: int = 1500) -> Iterator[str]:
        last_exc: Exception | None = None
        for provider in self._providers:
            try:
                yield from provider.stream(messages, max_tokens)
                return
            except Exception as exc:
                log.warning("Provider '%s' stream failed, trying next: %s", provider.model_id, exc)
                last_exc = exc
        raise RuntimeError("All LLM providers failed for streaming") from last_exc
