"""
routers/agent.py — POST /ask/agent endpoint.

Uses LegalAgent (multi-hop agentic RAG) instead of single-pass retrieve+generate.
Only invoked for COMPLEX queries; SIMPLE queries are redirected to the standard /ask
endpoint to save tokens.

Streaming variant (POST /ask/agent/stream) emits SSE events showing intermediate
tool calls and observations, so the user sees the agent "thinking".

SSE event types emitted by /ask/agent/stream:
    {"type": "complexity",  "value": "complex"|"simple",   ...}
    {"type": "step",        "step":  str,  "iteration": int}
    {"type": "tool",        "tool":  str,  "args":  dict}
    {"type": "obs",         "text":  str}  — truncated observation
    {"type": "sources",     "sources": [...]}
    {"type": "answer",      "text":  str,  "iterations": int}
    {"type": "error",       "detail": str}
    {"type": "done",        "model_used": str, "iterations": int}
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.dependencies import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    check_rate_limit,
    chunk_to_source,
    client_ip,
    compute_confidence,
    init_retriever,
    is_internal_request,
    verify_api_token,
)
from api.schemas import AskRequest, AskResponse

log = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_agent():
    """
    Build (and cache) a LegalAgent instance.

    The agent is cached as a module-level singleton — same pattern as init_retriever().
    """
    global _agent  # noqa: PLW0603
    if _agent is not None:
        return _agent

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured — agent endpoint unavailable.",
        )

    import openai

    from rag.agent import LegalAgent

    retriever = init_retriever()
    llm_client = openai.OpenAI(api_key=OPENAI_API_KEY)
    _agent = LegalAgent(
        retriever=retriever,
        llm_client=llm_client,
        llm_model=OPENAI_MODEL,
        max_iterations=6,
        temperature=0.1,
    )
    log.info("LegalAgent initialised (model=%s, max_iterations=6)", OPENAI_MODEL)
    return _agent


_agent = None


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── Non-streaming endpoint ─────────────────────────────────────────────────────


@router.post("/ask/agent", response_model=AskResponse, tags=["agent"])
async def ask_agent(request: AskRequest, req: Request) -> AskResponse:
    """
    Multi-hop agentic RAG for complex Polish legal questions.

    For SIMPLE or TRIVIAL queries the endpoint falls back to standard single-pass
    RAG to avoid unnecessary LLM calls.  Complexity is determined by the same
    classifier used in LegalRetriever._classify_complexity().
    """
    if not is_internal_request(req) and not await verify_api_token(req):
        check_rate_limit(client_ip(req))

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    log.info("Agent /ask/agent: %r", question[:120])

    # ── Complexity gate ────────────────────────────────────────────────────────
    retriever = init_retriever()
    from rag.retriever import QueryComplexity
    complexity = retriever._classify_complexity(question)
    log.info("Query complexity: %s", complexity.value)

    if complexity != QueryComplexity.COMPLEX:
        # Delegate to standard single-pass retrieval to save tokens
        log.info("Non-complex query — falling back to standard RAG")
        from api.dependencies import build_prompt, generate_answer

        chunks = await asyncio.to_thread(
            functools.partial(retriever.retrieve, query=question, top_k=request.top_k)
        )
        context_str = retriever.format_context(chunks, max_chars=8000)
        prompt = build_prompt(question, context_str)
        answer, model_used = await asyncio.to_thread(generate_answer, prompt)

        return AskResponse(
            question=question,
            answer=answer,
            sources=[chunk_to_source(c) for c in chunks],
            model_used=model_used,
            retrieval_used=bool(chunks),
            confidence=compute_confidence(chunks),
        )

    # ── Agent path ─────────────────────────────────────────────────────────────
    agent = _get_agent()
    try:
        result = await asyncio.to_thread(functools.partial(agent.run, question))
    except Exception as exc:
        log.error("Agent run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    sources = [chunk_to_source(c) for c in result.sources]
    return AskResponse(
        question=question,
        answer=result.answer,
        sources=sources,
        model_used=OPENAI_MODEL,
        retrieval_used=bool(result.sources),
        confidence=compute_confidence(result.sources),
    )


# ── Streaming endpoint ─────────────────────────────────────────────────────────


@router.post("/ask/agent/stream", tags=["agent"])
async def ask_agent_stream(request: AskRequest, req: Request) -> StreamingResponse:
    """
    Streaming version of /ask/agent.

    Emits SSE events as the agent reasons:
    - complexity event (first) — so the client can decide to show a spinner
    - step / tool / obs events — agent intermediate work
    - sources event — all retrieved documents
    - done event — final answer and metadata
    """
    if not is_internal_request(req) and not await verify_api_token(req):
        check_rate_limit(client_ip(req))

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    async def event_stream() -> AsyncGenerator[str, None]:
        retriever = init_retriever()
        from rag.retriever import QueryComplexity
        complexity = retriever._classify_complexity(question)
        log.info("Agent stream: complexity=%s for %r", complexity.value, question[:80])

        yield _sse({"type": "complexity", "value": complexity.value})

        if complexity != QueryComplexity.COMPLEX:
            # Simple path: standard RAG with a single streaming generation
            yield _sse({
                "type": "step",
                "step": "Zapytanie proste — używam standardowego wyszukiwania.",
                "iteration": 1,
            })
            try:
                chunks = await asyncio.to_thread(
                    functools.partial(retriever.retrieve, query=question, top_k=request.top_k)
                )
            except Exception as exc:
                yield _sse({"type": "error", "detail": f"Błąd wyszukiwania: {exc}"})
                return

            sources = [chunk_to_source(c) for c in chunks]
            yield _sse({"type": "sources", "sources": [s.model_dump() for s in sources]})

            context_str = retriever.format_context(chunks, max_chars=8000)
            from api.dependencies import build_prompt, SYSTEM_PROMPT

            if not OPENAI_API_KEY:
                yield _sse({"type": "error", "detail": "OPENAI_API_KEY not set"})
                return

            import openai as _openai
            client = _openai.OpenAI(api_key=OPENAI_API_KEY)
            prompt = build_prompt(question, context_str)
            try:
                stream = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=1500,
                    stream=True,
                    timeout=90,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield _sse({"type": "delta", "text": delta})
            except Exception as exc:
                yield _sse({"type": "error", "detail": str(exc)})
                return

            yield _sse({
                "type": "done",
                "model_used": OPENAI_MODEL,
                "iterations": 1,
                "confidence": compute_confidence(chunks).model_dump(),
            })
            return

        # ── Complex path: agentic loop ─────────────────────────────────────────
        if not OPENAI_API_KEY:
            yield _sse({"type": "error", "detail": "OPENAI_API_KEY not set"})
            return

        agent = _get_agent()
        try:
            async for event in agent.run_stream(question):
                if event.get("type") == "answer":
                    # Emit sources first, then final answer
                    raw_sources = event.get("sources", [])
                    yield _sse({"type": "sources", "sources": raw_sources})
                    yield _sse({
                        "type": "done",
                        "model_used": OPENAI_MODEL,
                        "answer": event.get("text", ""),
                        "iterations": event.get("iterations", 0),
                    })
                else:
                    yield _sse(event)
        except Exception as exc:
            log.error("Agent stream event loop error: %s", exc, exc_info=True)
            yield _sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
