"""Router: /ask and /ask/stream endpoints."""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.schemas import AskRequest, AskResponse
from api.result_cache import get_cache
from api.dependencies import (
    is_internal_request, verify_api_token, client_ip, check_rate_limit,
    init_retriever, generate_answer, get_llm_provider, build_prompt, chunk_to_source,
    compute_confidence, resolve_publisher_filter,
    SYSTEM_PROMPT,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, req: Request) -> AskResponse:
    if not is_internal_request(req) and not await verify_api_token(req):
        check_rate_limit(client_ip(req))

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    log.info("Question: %s", question[:120])

    _cache = get_cache()
    cached = _cache.get(question, request.source_type_filter, request.top_k)
    if cached is not None:
        log.info("Cache HIT")
        return JSONResponse(cached)

    retrieved_chunks = []
    context_str = ""
    retrieval_used = False

    if request.use_rag:
        try:
            retriever = init_retriever()
            pub_filter = resolve_publisher_filter(request.source_type_filter, request.publisher_filter)
            chunks = await asyncio.to_thread(functools.partial(
                retriever.retrieve,
                query=question,
                top_k=request.top_k,
                year_filter=request.year_filter,
                year_from=request.year_from,
                year_to=request.year_to,
                publisher_filter=pub_filter,
                source_type_filter=request.source_type_filter,
                exclude_repealed=request.exclude_repealed,
                as_of_year=request.as_of_year,
            ))
            context_str = retriever.format_context(chunks, max_chars=8000)
            retrieved_chunks = chunks
            retrieval_used = True
        except Exception as exc:
            log.warning("RAG retrieval failed: %s", exc)

    prompt = build_prompt(question, context_str)

    if request.history:
        try:
            provider = get_llm_provider()
            if provider is None:
                raise RuntimeError("No LLM provider configured")
            msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
            for turn in request.history[-6:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    msgs.append({"role": role, "content": content[:2000]})
            msgs.append({"role": "user", "content": prompt})
            answer, model_used = await asyncio.to_thread(provider.generate, msgs)
        except Exception as exc:
            log.warning("Multi-turn /ask failed, falling back: %s", exc)
            answer, model_used = await asyncio.to_thread(generate_answer, prompt)
    else:
        answer, model_used = await asyncio.to_thread(generate_answer, prompt)

    sources = [chunk_to_source(c) for c in retrieved_chunks]
    response = AskResponse(
        question=question, answer=answer, sources=sources,
        model_used=model_used, retrieval_used=retrieval_used,
        confidence=compute_confidence(retrieved_chunks),
    )
    _cache.set(question, request.source_type_filter, request.top_k, response.model_dump())
    return response


@router.post("/ask/stream")
async def ask_stream(request: AskRequest, req: Request) -> StreamingResponse:
    if not is_internal_request(req) and not await verify_api_token(req):
        check_rate_limit(client_ip(req))

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    async def event_stream() -> AsyncGenerator[str, None]:
        def sse(payload: dict) -> str:
            return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        retrieved_chunks = []
        context_str = ""
        retrieval_used = False

        if request.use_rag:
            try:
                retriever = init_retriever()
                pub_filter = resolve_publisher_filter(request.source_type_filter, request.publisher_filter)
                chunks = await asyncio.to_thread(functools.partial(
                    retriever.retrieve,
                    query=question,
                    top_k=request.top_k,
                    year_filter=request.year_filter,
                    year_from=request.year_from,
                    year_to=request.year_to,
                    publisher_filter=pub_filter,
                    source_type_filter=request.source_type_filter,
                    exclude_repealed=request.exclude_repealed,
                    as_of_year=request.as_of_year,
                ))
                context_str = retriever.format_context(chunks, max_chars=8000)
                retrieved_chunks = chunks
                retrieval_used = True
            except Exception as exc:
                log.warning("RAG retrieval failed in stream: %s", exc)

        sources = [chunk_to_source(c) for c in retrieved_chunks]
        yield sse({"type": "sources", "sources": [s.model_dump() for s in sources],
                   "retrieval_used": retrieval_used})

        prompt = build_prompt(question, context_str)

        provider = get_llm_provider()
        if provider is None:
            yield sse({"type": "error", "detail": "Brak skonfigurowanego modelu językowego."})
            return

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if request.history:
            for turn in request.history[-6:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content[:2000]})
        messages.append({"role": "user", "content": prompt})

        try:
            deadline = time.time() + 90
            for delta in provider.stream(messages, max_tokens=1500):
                if time.time() > deadline:
                    yield sse({"type": "error", "detail": "Generacja przekroczyła limit czasu."})
                    return
                yield sse({"type": "delta", "text": delta})
        except Exception as exc:
            log.error("Streaming generation failed: %s", exc)
            yield sse({"type": "error", "detail": "Błąd generowania odpowiedzi."})
            return

        yield sse({"type": "done", "model_used": provider.model_id,
                   "confidence": compute_confidence(retrieved_chunks).model_dump()})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
