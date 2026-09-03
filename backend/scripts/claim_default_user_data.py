import argparse
import json

from app.db.database import SessionLocal
from app.services.ownership_claim import OwnershipClaimError, claim_default_user_data


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claim legacy Chrono ownership for one existing authenticated user"
    )
    parser.add_argument("--email", required=True, help="email of an existing Chrono user")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="report changes without writing")
    mode.add_argument("--apply", action="store_true", help="apply all changes atomically")
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    print("BACKUP_REQUIRED: create and verify a PostgreSQL backup before --apply")
    db = SessionLocal()
    try:
        result = claim_default_user_data(db, email=args.email, apply=args.apply)
        print(json.dumps(result.as_dict(), sort_keys=True))
    except OwnershipClaimError as exc:
        db.rollback()
        raise SystemExit(f"CLAIM_REFUSED: {exc}") from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
