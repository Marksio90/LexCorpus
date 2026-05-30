"""Router: private collection endpoints."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from api.schemas import AskRequest, AskResponse
from api.dependencies import (
    is_internal_request, verify_api_token,
    init_retriever, generate_answer, build_prompt, chunk_to_source, compute_confidence,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/internal/enqueue-document")
async def enqueue_document(req: Request) -> dict:
    if not is_internal_request(req):
        raise HTTPException(status_code=403, detail="Brak dostępu.")
    body = await req.json()
    doc_id    = body.get("doc_id")
    user_id   = body.get("user_id")
    file_path = body.get("file_path")
    mime_type = body.get("mime_type", "application/octet-stream")
    if not (doc_id and user_id and file_path):
        raise HTTPException(status_code=422, detail="Wymagane: doc_id, user_id, file_path")
    try:
        from api.tasks import process_private_document
        task = process_private_document.apply_async(
            args=[doc_id, user_id, file_path, mime_type],
            task_id=f"doc-{doc_id}",
        )
        log.info("Zakolejkowano task %s dla doc %s", task.id, doc_id)
        return {"task_id": task.id, "status": "queued"}
    except Exception as exc:
        log.error("Błąd kolejkowania: %s", exc)
        raise HTTPException(status_code=503, detail=f"Kolejka niedostępna: {exc}")


@router.delete("/private-collection/{user_id}")
async def delete_private_collection(user_id: str, req: Request) -> dict:
    token_owner = await verify_api_token(req)
    if not token_owner:
        raise HTTPException(status_code=401, detail="Wymagany token Bearer.")
    if token_owner != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu do tej kolekcji.")
    collection = f"lexcorpus_private_{user_id}"
    try:
        retriever = init_retriever()
        retriever.client.delete_collection(collection)
        log.info("Usunięto kolekcję %s", collection)
    except Exception as e:
        log.warning("Nie można usunąć kolekcji %s: %s", collection, e)
    return {"ok": True}


@router.post("/ask/private")
async def ask_private(request: AskRequest, req: Request) -> AskResponse:
    user_id = await verify_api_token(req)
    if not user_id:
        raise HTTPException(status_code=401, detail="Wymagany token API lub sesja.")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pytanie nie może być puste.")

    retriever = init_retriever()
    private_collection = f"lexcorpus_private_{user_id}"
    all_chunks = []

    try:
        public_chunks = await asyncio.to_thread(retriever.retrieve, question, request.top_k or 5)
        all_chunks.extend(public_chunks)
    except Exception as e:
        log.warning("Błąd retrieval publiczny: %s", e)

    try:
        query_vec = retriever.embed_query(question)
        priv_results = retriever.client.search(
            collection_name=private_collection,
            query_vector=query_vec,
            limit=5,
            with_payload=True,
        )
        for r in priv_results:
            from rag.retriever import RetrievedChunk
            chunk = RetrievedChunk(
                act_id=r.payload.get("doc_id", "private"),
                chunk_index=r.payload.get("chunk_index", 0),
                title="[Prywatny dokument]",
                year=None, publisher="PRIVATE", source_type="private",
                text=r.payload.get("text", ""),
                score=r.score, url=None, total_chunks=1,
            )
            all_chunks.append(chunk)
    except Exception as e:
        log.debug("Brak prywatnej kolekcji lub błąd: %s", e)

    if retriever.use_rerank and all_chunks:
        all_chunks = retriever._rerank(question, all_chunks)

    context_str = retriever.format_context(all_chunks[:8], max_chars=8000)
    prompt = build_prompt(question, context_str)
    answer, model_used = await asyncio.to_thread(generate_answer, prompt)
    sources = [chunk_to_source(c) for c in all_chunks[:8]]

    return AskResponse(
        question=question, answer=answer, sources=sources,
        model_used=model_used, retrieval_used=True,
        confidence=compute_confidence(all_chunks[:8]),
    )
