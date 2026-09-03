from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def ensure_schema_compatibility() -> None:
    """Apply additive, data-preserving compatibility changes for existing installs."""
    statements = (
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_provider VARCHAR(50)",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(255)",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_error_category VARCHAR(50)",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_error_provider VARCHAR(50)",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_error_model VARCHAR(255)",
        "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding_error_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS ix_memory_chunks_embedding_signature "
        "ON memory_chunks (embedding_provider, embedding_model, embedding_dimensions)",
        "ALTER TABLE google_drive_events ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)",
        "CREATE INDEX IF NOT EXISTS ix_google_drive_events_user_id "
        "ON google_drive_events (user_id)",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
