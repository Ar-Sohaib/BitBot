"""Initialise la base SQLite et crée les tables du schéma."""
from __future__ import annotations

import logging
from pathlib import Path

from src.config import load_settings
from src.storage.db import Database


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    log = logging.getLogger("init_db")

    settings = load_settings()
    schema_path = Path(__file__).resolve().parent.parent / "storage" / "schema.sql"

    log.info("DB path: %s", settings.db_path)
    db = Database(settings.db_path)
    db.init_schema(schema_path)
    log.info("Schema applied successfully.")
    db.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
