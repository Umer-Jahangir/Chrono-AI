from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.memories import router as memories_router
from app.api.timeline import router as timeline_router
from app.api.search import router as search_router
from app.api.google_drive import router as google_drive_router
from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.db.database import Base, engine, ensure_schema_compatibility
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk, User
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    yield


app = FastAPI(
    title="Chrono AI API",
    version="0.1.0",
    lifespan=lifespan,
)

frontend_origins = [origin.strip() for origin in settings.FRONTEND_ORIGINS.split(",") if origin.strip()]
if "*" in frontend_origins:
    raise RuntimeError("FRONTEND_ORIGINS must not contain '*' when authentication is enabled")
if frontend_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-N8N-Secret"],
    )

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(memories_router)
app.include_router(timeline_router)
app.include_router(search_router)
app.include_router(google_drive_router)
app.include_router(ask_router)

@app.get("/")
def root():
    return {
        "name": "Chrono AI",
        "status": "running",
    }
