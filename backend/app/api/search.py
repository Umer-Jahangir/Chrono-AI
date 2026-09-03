from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Memory, User
from app.services.auth import get_current_user
from app.services.metadata_normalizer import normalize_memory
from app.services.output_safety import redact_public_text
from app.services.retrieval import hybrid_search, make_excerpt


router = APIRouter(prefix="/search", tags=["Search"])


@router.get("")
def search_memories(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    source: str | None = None,
    event_type: str | None = None,
    mime_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    results, mode = hybrid_search(
        db,
        user_id=str(current_user.id),
        query_text=q,
        limit=limit,
        source=source,
        event_type=event_type,
        mime_type=mime_type,
        start=start,
        end=end,
    )
    memory_ids = list(dict.fromkeys(result["memory_id"] for result in results))
    memories = {
        str(memory.id): normalize_memory(memory)
        for memory in db.query(Memory).filter(
            Memory.user_id == str(current_user.id), Memory.id.in_(memory_ids)
        ).all()
    } if memory_ids else {}
    public_results = [
        {
            "score": result["score"],
            "title": result["title"],
            "excerpt": redact_public_text(make_excerpt(result["content"], q)),
            "source": result["source"],
            "event_type": result["event_type"],
            "event_date": result["event_date"],
            "open_url": memories.get(result["memory_id"]).open_url
            if memories.get(result["memory_id"]) else None,
        }
        for result in results
    ]
    return {"query": q, "mode": mode, "count": len(public_results), "results": public_results}
