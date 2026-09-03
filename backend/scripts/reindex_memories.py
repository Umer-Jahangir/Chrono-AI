import argparse
import json

from sqlalchemy import text

from app.core.config import settings
from app.db.database import Base, SessionLocal, engine, ensure_schema_compatibility
from app.services.embedding_reindexer import reindex_embeddings


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely resume Chrono chunk embeddings")
    parser.add_argument(
        "--missing-only",
        dest="missing_only",
        action="store_true",
        default=True,
        help="embed only missing, stale, or mismatched chunks (default)",
    )
    parser.add_argument(
        "--all",
        dest="missing_only",
        action="store_false",
        help="force re-embedding of all chunks",
    )
    parser.add_argument(
        "--user-id",
        help="internal Chrono user UUID (defaults to CHRONO_N8N_OWNER_USER_ID)",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    user_id = (args.user_id or settings.CHRONO_N8N_OWNER_USER_ID).strip()
    if not user_id and settings.ALLOW_LEGACY_DEFAULT_USER:
        user_id = "default"
    if not user_id:
        raise SystemExit(
            "Set CHRONO_N8N_OWNER_USER_ID or pass --user-id; legacy default ownership is disabled"
        )
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()

    db = SessionLocal()
    try:
        result = reindex_embeddings(
            db,
            user_id=user_id,
            missing_only=args.missing_only,
            report=lambda event: print(json.dumps({"embedding_error": event}, ensure_ascii=True)),
        )
        print(json.dumps(result, ensure_ascii=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
