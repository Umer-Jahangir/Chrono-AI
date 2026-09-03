from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Memory, User
from app.schemas.memory import MemoryCreate, MemoryResponse
from app.schemas.rag import StructuredItem
from app.services.auth import get_current_user
from app.api.timeline import memory_public_item


router = APIRouter(
    prefix="/memories",
    tags=["Memories"],
)


@router.post(
    "",
    response_model=MemoryResponse,
)
def create_memory(
    data: MemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memory = Memory(user_id=str(current_user.id), **data.model_dump())

    db.add(memory)
    db.commit()
    db.refresh(memory)

    return memory


@router.get(
    "",
    response_model=list[StructuredItem],
)
def get_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memories = (
        db.query(Memory)
        .filter(Memory.user_id == str(current_user.id))
        .order_by(Memory.event_date.desc())
        .all()
    )
    return [memory_public_item(memory) for memory in memories]
