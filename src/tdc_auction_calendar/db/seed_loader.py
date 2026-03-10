"""Idempotent seed loader — reads JSON files from db/seed/ and populates the DB."""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.jurisdiction import CountyInfoRow, StateRulesRow

SEED_DIR = Path(__file__).parent / "seed"

logger = structlog.get_logger()

# Maps seed filename stem to (ORM class, primary key column(s))
_SEED_MAP: dict[str, tuple[type, list[str]]] = {
    "states": (StateRulesRow, ["state"]),
    "counties": (CountyInfoRow, ["fips_code"]),
}


def load_seeds(session: Session) -> None:
    """Load all JSON seed files into the database idempotently.

    For each row, checks if a record with the same primary key already
    exists. If so, skips it; otherwise, inserts it.
    """
    for stem, (model_cls, pk_cols) in _SEED_MAP.items():
        seed_file = SEED_DIR / f"{stem}.json"
        if not seed_file.exists():
            logger.info("seed_file_missing", file=str(seed_file))
            continue

        rows = json.loads(seed_file.read_text())
        inserted = 0
        skipped = 0

        for row_data in rows:
            pk_filter = {col: row_data[col] for col in pk_cols}
            exists = session.query(model_cls).filter_by(**pk_filter).first()
            if exists:
                skipped += 1
                continue
            session.add(model_cls(**row_data))
            inserted += 1

        session.commit()
        logger.info(
            "seed_loaded",
            file=stem,
            inserted=inserted,
            skipped=skipped,
        )
