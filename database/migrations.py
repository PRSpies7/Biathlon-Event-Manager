"""Small SQLite migration helpers shared by the two existing databases."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def backup_database(path):
    """Use SQLite's backup API so committed WAL data is included."""
    path = Path(path)
    if not path.exists() or not path.stat().st_size:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = path.with_name(f"{path.stem}.before-seasons-{stamp}.sqlite")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    return destination


def execute_schema(conn, schema):
    """Execute our plain DDL without executescript's implicit commit."""
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)


def validate_season(season_year, *, required=False):
    if season_year is None and not required:
        return
    if type(season_year) is not int or not 1900 <= season_year <= 9999:
        raise ValueError("Select a Season between 1900 and 9999.")
