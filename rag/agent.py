"""
agent.py — Agentic multi-hop RAG for complex Polish legal queries.

No LangGraph dependency. Implements a clean tool-calling loop pattern:
  1. LLM decides which tool to call and with what arguments.
  2. The tool runs; its observation is appended to the context window.
  3. LLM decides whether more retrieval is needed or synthesizes the answer.
  4. Loop continues up to max_iterations.

Designed for cross-act queries such as:
  "Jak ustawa o VAT odnosi się do Kodeksu spółek handlowych w kontekście
   transakcji między spółkami powiązanymi?"

Usage as module:
    from rag.agent import LegalAgent, AgentResult
    from rag.retriever import LegalRetriever
    import openai

    retriever = LegalRetriever(...)
    client = openai.OpenAI(api_key="...")
    agent = LegalAgent(retriever=retriever, llm_client=client)
    result = agent.run("Jak ustawa o VAT odnosi się do KSH?")
    print(result.answer)
    for step in result.reasoning_steps:
        print(" •", step)
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from rag.retriever import LegalRetriever, RetrievedChunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

ISAP_TEXT_URL = "https://api.sejm.gov.pl/eli/acts/{eli}/text.html"
ISAP_ARTICLE_SEARCH_URL = "https://api.sejm.gov.pl/eli/acts/search"
ISAP_REQUEST_TIMEOUT = 15.0
ISAP_MAX_ARTICLE_CHARS = 2000  # cap article text returned to the LLM

# Token budget: do not let the accumulated context exceed this many chars before
# forcing the LLM to synthesize.  ~50k chars ≈ ~12k tokens for most LLMs.
MAX_CONTEXT_CHARS = 50_000

# JSON function-call schema sent to the LLM
TOOLS_SCHEMA: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve",
            "description": (
                "Wyszukuje fragmenty polskich aktów prawnych lub orzeczeń sądowych "
                "pasujące do podanego zapytania. Zwraca cytaty z pełnymi metadanymi. "
                "Wywołaj kilka razy z różnymi zapytaniami, aby zebrać informacje "
                "ze wszystkich potrzebnych aktów."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Zapytanie w języku polskim, np. "
                            "'przepisy VAT dotyczące transakcji między podmiotami powiązanymi'"
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Liczba fragmentów do zwrócenia (domyślnie 5, max 10).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_article",
            "description": (
                "Pobiera treść konkretnego artykułu lub paragrafu z ISAP "
                "na podstawie identyfikatora aktu prawnego (act_id / ELI) "
                "i numeru artykułu. Przydatne gdy wiesz, który konkretny przepis "
                "jest potrzebny."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "act_id": {
                        "type": "string",
                        "description": (
                            "ELI aktu prawnego, np. 'WDU20040540535' lub "
                            "'pl/2004/u/535'. Można uzyskać z wyników retrieve()."
                        ),
                    },
                    "article_number": {
                        "type": "string",
                        "description": (
                            "Numer artykułu lub paragrafu, np. '86', '86a', '4a', '§ 3'."
                        ),
                    },
                },
                "required": ["act_id", "article_number"],
            },
        },
    },
]

# System prompt directing the agent to reason step-by-step in Polish
AGENT_SYSTEM_PROMPT = """\
Jesteś zaawansowanym asystentem prawnym specjalizującym się w polskim prawie.
Twoim zadaniem jest udzielenie wyczerpującej odpowiedzi na złożone pytanie \
prawne wymagające analizy wielu aktów prawnych.

INSTRUKCJA DZIAŁANIA:
1. Przemyśl, jakie informacje prawne są potrzebne do odpowiedzi (myśl krok po kroku).
2. Wywołaj narzędzie `retrieve(query)`, aby wyszukać odpowiednie przepisy i orzeczenia.
3. W razie potrzeby wywołaj `lookup_article(act_id, article_number)` dla konkretnych artykułów.
4. Możesz wywołać narzędzia wielokrotnie — dla różnych ustaw, aspektów prawnych, itd.
5. Gdy masz wystarczający kontekst, odpowiedz na pytanie w języku polskim, \
cytując przepisy za pomocą [n] gdzie n to numer źródła.

ZASADY:
- Odpowiadaj WYŁĄCZNIE na podstawie znalezionych przepisów.
- Nie spekuluj ani nie wymyślaj treści przepisów.
- Jeśli przepisy nie dają podstawy do odpowiedzi, powiedz o tym wprost.
- Zawsze wskazuj relacje między różnymi aktami prawnymi gdy pytanie tego dotyczy.
- Cytuj konkretne artykuły, np. "zgodnie z art. 32 ust. 1 ustawy o VAT [1]".
"""


# ── Data models ────────────────────────────────────────────────────────────────


@dataclass
class AgentResult:
    """Final result returned by LegalAgent.run()."""

    answer: str
    """Synthesized answer in Polish, with [n] citation markers."""

    reasoning_steps: list[str]
    """Human-readable log of each reasoning step (tool call + observation summary)."""

    sources: list[RetrievedChunk]
    """All unique RetrievedChunk objects collected across iterations."""

    iterations: int
    """Number of LLM calls consumed."""

    tools_used: list[str]
    """Ordered list of tool names that were called, e.g. ['retrieve', 'retrieve', 'lookup_article']."""


@dataclass
class ToolCall:
    """Parsed tool invocation from the LLM response."""

    name: str
    arguments: dict[str, Any]
    call_id: str = ""


# ── Tools ──────────────────────────────────────────────────────────────────────


class LegalTool(ABC):
    """Abstract base class for agent tools."""

    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: Any) -> str:
        """Execute the tool and return a string observation."""


class RetrieveTool(LegalTool):
    """
    Hybrid search over the Qdrant corpus.

    Wraps LegalRetriever.retrieve() and formats results as a numbered
    citation block suitable for the LLM's context window.
    """

    name = "retrieve"
    description = "Wyszukuje fragmenty aktów prawnych i orzeczeń z korpusu."

    def __init__(self, retriever: LegalRetriever) -> None:
        self.retriever = retriever
        self._all_chunks: list[RetrievedChunk] = []  # accumulator, read by LegalAgent

    def run(self, query: str, top_k: int = 5) -> str:  # type: ignore[override]
        top_k = min(int(top_k), 10)
        log.info("RetrieveTool: query=%r top_k=%d", query[:80], top_k)
        try:
            chunks = self.retriever.retrieve(query, top_k=top_k)
        except Exception as exc:
            log.warning("RetrieveTool failed: %s", exc)
            return f"[BŁĄD WYSZUKIWANIA] {exc}"

        if not chunks:
            return "Nie znaleziono pasujących dokumentów dla zapytania: " + query

        # Accumulate unique chunks (by act_id + chunk_index)
        seen_keys = {f"{c.act_id}___{c.chunk_index}" for c in self._all_chunks}
        for c in chunks:
            k = f"{c.act_id}___{c.chunk_index}"
            if k not in seen_keys:
                self._all_chunks.append(c)
                seen_keys.add(k)

        # Format as numbered blocks for the LLM
        lines: list[str] = [f"Wyniki wyszukiwania dla: «{query}»\n"]
        for i, chunk in enumerate(chunks, 1):
            cit = chunk.citation()
            lines.append(f"[{i}] {cit}")
            preview = chunk.text[:600].replace("\n", " ")
            if len(chunk.text) > 600:
                preview += "…"
            lines.append(preview)
            lines.append("")
        return "\n".join(lines)


class LookupActTool(LegalTool):
    """
    Fetches a specific article from the ISAP Sejm REST API by act ELI and
    article number.  Returns the raw HTML-stripped text of the article.

    Falls back gracefully if the ISAP API is unavailable.
    """

    name = "lookup_article"
    description = "Pobiera konkretny artykuł z ISAP na podstawie identyfikatora aktu i numeru artykułu."

    # Pattern to locate an article in the fetched HTML/text
    _ARTICLE_RE = re.compile(
        r"(?:^|\n)\s*(?:Art\.|Artykuł)\s+{number}(?:\s|[. ])",
        re.IGNORECASE | re.MULTILINE,
    )
    _PARA_RE = re.compile(
        r"(?:^|\n)\s*§\s*{number}(?:\s|[. ])",
        re.IGNORECASE | re.MULTILINE,
    )

    def run(self, act_id: str, article_number: str) -> str:  # type: ignore[override]
        log.info("LookupActTool: act_id=%r article=%r", act_id, article_number)

        # Normalise act_id to ELI path format if it looks like a raw WDU code
        eli = self._normalise_eli(act_id)

        url = ISAP_TEXT_URL.format(eli=eli)
        try:
            with httpx.Client(timeout=ISAP_REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        ),
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "pl-PL,pl;q=0.9",
                    },
                )
        except httpx.RequestError as exc:
            log.warning("LookupActTool HTTP error: %s", exc)
            return f"[BŁĄD POŁĄCZENIA Z ISAP] {exc}"

        if resp.status_code != 200:
            return (
                f"[ISAP zwrócił status {resp.status_code} dla aktu {act_id}. "
                "Spróbuj użyć retrieve() z bardziej precyzyjnym zapytaniem.]"
            )

        raw = resp.text
        # Strip HTML tags for cleaner text
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

        excerpt = self._extract_article(text, article_number)
        if not excerpt:
            # Return a short window around the first keyword match as fallback
            pattern = re.compile(
                rf"\bart\.?\s*{re.escape(article_number)}\b",
                re.IGNORECASE,
            )
            m = pattern.search(text)
            if m:
                start = max(0, m.start() - 50)
                end = min(len(text), m.end() + ISAP_MAX_ARTICLE_CHARS)
                excerpt = text[start:end]
            else:
                return (
                    f"[Nie znaleziono artykułu {article_number} w akcie {act_id}. "
                    "Sprawdź numer artykułu lub użyj retrieve().]"
                )

        return (
            f"Treść art. {article_number} z aktu {act_id}:\n\n"
            + excerpt[:ISAP_MAX_ARTICLE_CHARS]
            + ("…" if len(excerpt) > ISAP_MAX_ARTICLE_CHARS else "")
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_eli(act_id: str) -> str:
        """
        Convert WDU-style act_id (e.g. 'WDU20040540535') to ELI path
        (e.g. 'WDU/2004/54/535') expected by the Sejm API.

        If act_id already contains slashes or looks like a proper ELI, return as-is.
        """
        if "/" in act_id or act_id.startswith("pl/"):
            return act_id
        # WDU20040540535  →  WDU/2004/54/535
        m = re.match(r"^(WDU|WMP)(\d{4})(\d{3,4})(\d{3,4})$", act_id)
        if m:
            pub, year, pos1, pos2 = m.groups()
            return f"{pub}/{year}/{int(pos1)}/{int(pos2)}"
        return act_id  # return unchanged if we can't parse it

    def _extract_article(self, text: str, article_number: str) -> str:
        """
        Locate the article in the plain-text act and return it together with
        the next article's opening line as a natural boundary.
        """
        # Try "Art. N" pattern
        pattern_str = article_number.replace(".", r"\.")
        art_re = re.compile(
            rf"(?:^|\n)\s*Art\.\s+{pattern_str}[.\s ]",
            re.IGNORECASE | re.MULTILINE,
        )
        # Try "§ N" pattern for ordinances / statutes that use paragraphs
        para_re = re.compile(
            rf"(?:^|\n)\s*§\s+{pattern_str}[.\s ]",
            re.IGNORECASE | re.MULTILINE,
        )

        for regex in (art_re, para_re):
            m = regex.search(text)
            if m:
                start = m.start()
                # Find the next article boundary
                next_art = re.search(
                    r"(?:^|\n)\s*(?:Art\.|§)\s+\d",
                    text[start + len(m.group()) :],
                    re.MULTILINE,
                )
                if next_art:
                    end = start + len(m.group()) + next_art.start()
                else:
                    end = start + ISAP_MAX_ARTICLE_CHARS
                return text[start:end].strip()
        return ""


# ── Agent ──────────────────────────────────────────────────────────────────────


class LegalAgent:
    """
    Agentic multi-hop RAG loop for complex Polish legal queries.

    The agent drives an LLM (OpenAI-compatible) through a tool-calling loop:
    - LLM is given the user question + tools schema + accumulated observations.
    - LLM either calls a tool (retrieve / lookup_article) or produces the final answer.
    - Loop runs up to max_iterations before forcing a synthesis.

    Args:
        retriever:      Initialised LegalRetriever instance.
        llm_client:     openai.OpenAI (or compatible) client.
        llm_model:      Model name, defaults to OPENAI_MODEL env var or gpt-4o-mini.
        max_iterations: Maximum number of LLM calls before forcing final answer.
        temperature:    Sampling temperature for the LLM (low = more deterministic).
    """

    def __init__(
        self,
        retriever: LegalRetriever,
        llm_client: Any,
        llm_model: str | None = None,
        max_iterations: int = 5,
        temperature: float = 0.1,
    ) -> None:
        import os

        self.retriever = retriever
        self.llm_client = llm_client
        self.llm_model = llm_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.max_iterations = max_iterations
        self.temperature = temperature

        # Initialise tools — RetrieveTool owns the chunks accumulator
        self._retrieve_tool = RetrieveTool(retriever)
        self._lookup_tool = LookupActTool()
        self.tools: list[LegalTool] = [self._retrieve_tool, self._lookup_tool]
        self._tool_map: dict[str, LegalTool] = {t.name: t for t in self.tools}

    # ── Public API ─────────────────────────────────────────────────────────────

    def run(self, query: str) -> AgentResult:
        """
        Execute the multi-hop reasoning loop for the given Polish legal query.

        Returns an AgentResult with the synthesized answer, all reasoning steps,
        all retrieved sources, and metadata about the run.
        """
        log.info("LegalAgent.run: %r", query[:120])

        messages: list[dict] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        reasoning_steps: list[str] = []
        tools_used: list[str] = []
        iterations = 0
        total_observation_chars = 0

        for iteration in range(self.max_iterations):
            iterations += 1
            log.info("Agent iteration %d/%d", iteration + 1, self.max_iterations)

            # Check context budget before calling LLM
            if total_observation_chars > MAX_CONTEXT_CHARS:
                log.info(
                    "Context budget exceeded (%d chars) — forcing synthesis",
                    total_observation_chars,
                )
                messages.append({
                    "role": "user",
                    "content": (
                        "Masz już wystarczającą ilość informacji. "
                        "Teraz wygeneruj pełną, szczegółową odpowiedź na oryginalne pytanie. "
                        "Nie wywołuj już żadnych narzędzi — tylko odpowiedz."
                    ),
                })
                response = self._call_llm(messages, use_tools=False)
                answer = response.choices[0].message.content or ""
                reasoning_steps.append(
                    f"[Iteracja {iteration + 1}] Przekroczono budżet kontekstu — synteza wymuszona."
                )
                break

            # Call LLM with tools
            response = self._call_llm(messages, use_tools=True)
            msg = response.choices[0].message

            # Add the assistant turn to the conversation
            messages.append(msg.to_dict() if hasattr(msg, "to_dict") else {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ] or None,
            })

            tool_calls = msg.tool_calls or []

            if not tool_calls:
                # LLM chose to answer directly — we're done
                answer = msg.content or ""
                reasoning_steps.append(
                    f"[Iteracja {iteration + 1}] LLM wygenerował odpowiedź końcową "
                    f"({len(answer)} znaków)."
                )
                log.info("Agent completed with direct answer at iteration %d", iteration + 1)
                break

            # Execute each tool call sequentially
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError as exc:
                    arguments = {}
                    log.warning("Failed to parse tool arguments %r: %s", tc.function.arguments, exc)

                log.info("Calling tool %r with %r", tool_name, arguments)
                tools_used.append(tool_name)

                tool = self._tool_map.get(tool_name)
                if tool is None:
                    observation = f"[Nieznane narzędzie: {tool_name}]"
                else:
                    try:
                        observation = tool.run(**arguments)
                    except TypeError as exc:
                        observation = f"[BŁĄD WYWOŁANIA NARZĘDZIA {tool_name}]: {exc}"
                    except Exception as exc:
                        log.error("Tool %r raised exception: %s", tool_name, exc, exc_info=True)
                        observation = f"[BŁĄD NARZĘDZIA {tool_name}]: {exc}"

                total_observation_chars += len(observation)

                step_summary = (
                    f"[Iteracja {iteration + 1}] Wywołano {tool_name}("
                    + ", ".join(f"{k}={v!r}" for k, v in list(arguments.items())[:2])
                    + f") → {len(observation)} znaków odpowiedzi."
                )
                reasoning_steps.append(step_summary)
                log.info(step_summary)

                # Append tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                })

        else:
            # Loop exhausted — force a final synthesis pass
            log.info("Agent hit max_iterations=%d — forcing final synthesis", self.max_iterations)
            messages.append({
                "role": "user",
                "content": (
                    "Przekroczono maksymalną liczbę kroków. "
                    "Na podstawie zebranych informacji wygeneruj teraz możliwie pełną odpowiedź "
                    "na oryginalne pytanie. Powołuj się na znalezione przepisy."
                ),
            })
            response = self._call_llm(messages, use_tools=False)
            answer = response.choices[0].message.content or ""
            iterations = self.max_iterations
            reasoning_steps.append(
                f"[Iteracja {self.max_iterations}] Wymuszona synteza po wyczerpaniu kroków."
            )

        return AgentResult(
            answer=answer.strip(),
            reasoning_steps=reasoning_steps,
            sources=list(self._retrieve_tool._all_chunks),
            iterations=iterations,
            tools_used=tools_used,
        )

    # ── Async variant ──────────────────────────────────────────────────────────

    async def run_async(self, query: str) -> AgentResult:
        """
        Async version of run() for use in FastAPI request handlers.
        Offloads the synchronous blocking loop to a thread pool.
        """
        import asyncio
        import functools

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self.run, query))

    async def run_stream(self, query: str):
        """
        Async generator that yields SSE-ready dicts as the agent progresses.

        Yielded event shapes:
            {"type": "step",   "step": str, "iteration": int}
            {"type": "tool",   "tool": str, "args": dict}
            {"type": "obs",    "text": str}
            {"type": "answer", "text": str, "sources": [...], "iterations": int}
            {"type": "error",  "detail": str}
        """
        import asyncio
        import functools
        import queue
        import threading

        event_queue: queue.Queue[dict | None] = queue.Queue()

        def _run_with_events() -> None:
            """Thread function: run the agent loop and push events to the queue."""
            try:
                messages: list[dict] = [
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ]
                total_observation_chars = 0

                for iteration in range(self.max_iterations):
                    event_queue.put({
                        "type": "step",
                        "step": f"Krok {iteration + 1}: analizuję pytanie i decyduję o kolejnym działaniu…",
                        "iteration": iteration + 1,
                    })

                    if total_observation_chars > MAX_CONTEXT_CHARS:
                        event_queue.put({
                            "type": "step",
                            "step": "Zebrано wystarczającą ilość informacji — syntetyzuję odpowiedź.",
                            "iteration": iteration + 1,
                        })
                        messages.append({
                            "role": "user",
                            "content": (
                                "Masz już wystarczającą ilość informacji. "
                                "Teraz wygeneruj pełną odpowiedź. Nie wywołuj narzędzi."
                            ),
                        })
                        resp = self._call_llm(messages, use_tools=False)
                        answer = resp.choices[0].message.content or ""
                        break

                    resp = self._call_llm(messages, use_tools=True)
                    msg = resp.choices[0].message
                    messages.append(msg.to_dict() if hasattr(msg, "to_dict") else {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in (msg.tool_calls or [])
                        ] or None,
                    })

                    tool_calls = msg.tool_calls or []
                    if not tool_calls:
                        answer = msg.content or ""
                        break

                    for tc in tool_calls:
                        tool_name = tc.function.name
                        try:
                            arguments = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                        event_queue.put({
                            "type": "tool",
                            "tool": tool_name,
                            "args": arguments,
                        })

                        tool = self._tool_map.get(tool_name)
                        if tool is None:
                            observation = f"[Nieznane narzędzie: {tool_name}]"
                        else:
                            try:
                                observation = tool.run(**arguments)
                            except Exception as exc:
                                observation = f"[BŁĄD]: {exc}"

                        total_observation_chars += len(observation)
                        event_queue.put({"type": "obs", "text": observation[:300] + (
                            "…" if len(observation) > 300 else ""
                        )})
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": observation,
                        })
                else:
                    messages.append({
                        "role": "user",
                        "content": "Wygeneruj teraz odpowiedź końcową.",
                    })
                    resp = self._call_llm(messages, use_tools=False)
                    answer = resp.choices[0].message.content or ""

                from rag.retriever import RetrievedChunk
                sources_raw = [c.as_dict() for c in self._retrieve_tool._all_chunks]
                event_queue.put({
                    "type": "answer",
                    "text": answer.strip(),
                    "sources": sources_raw,
                    "iterations": len([e for e in [] if e]),  # placeholder
                })
            except Exception as exc:
                log.error("Agent stream error: %s", exc, exc_info=True)
                event_queue.put({"type": "error", "detail": str(exc)})
            finally:
                event_queue.put(None)  # sentinel

        thread = threading.Thread(target=_run_with_events, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()
        while True:
            # Poll queue in an async-friendly way
            event = await loop.run_in_executor(None, event_queue.get)
            if event is None:
                break
            yield event

    # ── Internals ──────────────────────────────────────────────────────────────

    def _call_llm(self, messages: list[dict], use_tools: bool = True) -> Any:
        """Call the LLM and return the raw completion response."""
        kwargs: dict[str, Any] = {
            "model": self.llm_model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 1024,
        }
        if use_tools:
            kwargs["tools"] = TOOLS_SCHEMA
            kwargs["tool_choice"] = "auto"

        max_retries = 3
        backoff = 2.0
        for attempt in range(max_retries):
            try:
                return self.llm_client.chat.completions.create(**kwargs)
            except Exception as exc:
                if attempt == max_retries - 1:
                    raise
                log.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1, max_retries, exc, backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        raise RuntimeError("LLM call failed after all retries")  # never reached


# ── Factory helper ─────────────────────────────────────────────────────────────


def make_agent(retriever: LegalRetriever, api_key: str | None = None) -> LegalAgent:
    """
    Convenience factory: creates a LegalAgent with an OpenAI client.

    Args:
        retriever: Initialised LegalRetriever.
        api_key:   OpenAI API key. Falls back to OPENAI_API_KEY env var.

    Returns:
        Ready-to-use LegalAgent instance.
    """
    import os

    import openai

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OpenAI API key required — pass api_key= or set OPENAI_API_KEY env var."
        )
    llm_client = openai.OpenAI(api_key=key)
    return LegalAgent(retriever=retriever, llm_client=llm_client)
