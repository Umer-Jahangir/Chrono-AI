"""Apply only the additive Chrono authentication schema changes."""

from sqlalchemy import text

from app.db.database import Base, engine, ensure_schema_compatibility
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk, User  # noqa: F401


def main() -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    print("Authentication schema is compatible; no ownership records were changed.")


if __name__ == "__main__":
    main()
