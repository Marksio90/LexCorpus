"""Router: /sync and /stats endpoints."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request

from api.schemas import StatsResponse, SourceBreakdown
from api.dependencies import require_internal, init_retriever, QDRANT_PATH, QDRANT_COLLECTION, EMBEDDING_MODEL, RERANK_ENABLED, EXPAND_ENABLED

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/sync/status")
async def sync_status(req: Request) -> dict:
    require_internal(req)
    from api.sync import get_status
    return get_status()


@router.post("/sync/trigger")
async def sync_trigger(req: Request) -> dict:
    require_internal(req)
    from api.sync import trigger_sync
    return trigger_sync()


@router.get("/stats", response_model=StatsResponse)
async def stats(req: Request) -> StatsResponse:
    require_internal(req)
    from datetime import datetime, timezone
    from qdrant_client.http import models as qmodels

    retriever = init_retriever()
    client = retriever.client

    publisher_map = {
        "legislation":        "WDU",
        "judgment_nsa":       "ADMINISTRATIVE",
        "judgment_sn":        "SUPREME",
        "judgment_tk":        "CONSTITUTIONAL_TRIBUNAL",
        "judgment_common":    "COMMON",
        "judgment_kio":       "NATIONAL_APPEAL_CHAMBER",
        "tax_interpretation": "KIS",
    }

    counts: dict[str, int] = {}
    for source_type, publisher in publisher_map.items():
        try:
            result = client.count(
                collection_name=QDRANT_COLLECTION,
                count_filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(key="publisher", match=qmodels.MatchValue(value=publisher))
                ]),
                exact=False,
            )
            counts[source_type] = result.count
        except Exception:
            counts[source_type] = 0

    total_chunks = sum(counts.values())
    breakdown = SourceBreakdown(total=total_chunks, **counts)

    last_ingest = None
    sentinel = Path(QDRANT_PATH.replace("http://qdrant:6333", "/app/data/qdrant")
                    if QDRANT_PATH.startswith("http") else QDRANT_PATH) / ".ingested"
    if sentinel.exists():
        mtime = sentinel.stat().st_mtime
        last_ingest = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    return StatsResponse(
        by_source=breakdown,
        total_chunks=total_chunks,
        collection_name=QDRANT_COLLECTION,
        embedding_model=EMBEDDING_MODEL,
        rerank_enabled=RERANK_ENABLED,
        expand_enabled=EXPAND_ENABLED,
        last_ingest=last_ingest,
    )
