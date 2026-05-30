"""Router: /search endpoint."""
from __future__ import annotations

import asyncio
import functools
import logging

from fastapi import APIRouter, Request

from api.schemas import SearchRequest, SearchResponse
from api.dependencies import (
    is_internal_request, verify_api_token, client_ip, check_rate_limit,
    init_retriever, chunk_to_source, resolve_publisher_filter,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, req: Request) -> SearchResponse:
    if not is_internal_request(req) and not await verify_api_token(req):
        check_rate_limit(client_ip(req))

    retriever = init_retriever()
    pub_filter = resolve_publisher_filter(request.source_type_filter, request.publisher_filter)
    chunks = await asyncio.to_thread(functools.partial(
        retriever.retrieve,
        query=request.query,
        top_k=request.top_k,
        year_filter=request.year_filter,
        year_from=request.year_from,
        year_to=request.year_to,
        publisher_filter=pub_filter,
        source_type_filter=request.source_type_filter,
        exclude_repealed=request.exclude_repealed,
        as_of_year=request.as_of_year,
    ))
    return SearchResponse(
        query=request.query,
        results=[chunk_to_source(c) for c in chunks],
        total=len(chunks),
    )
