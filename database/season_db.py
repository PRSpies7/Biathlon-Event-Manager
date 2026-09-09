"""Season-only schema and configuration using the application's SQLite layer.

One file is one season. No season table is coupled to workflow sessions.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

from .db import get_conn

SCHEMA = """
CREATE TABLE IF NOT EXISTS season_record_templates (
    id INTEGER PRIMARY KEY CHECK(id=1),
    source_filename TEXT NOT NULL,
    content BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS season_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity TEXT NOT NULL,
    name TEXT NOT NULL,
    event_date TEXT NOT NULL,
    competition_type TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE(identity, event_date, competition_type)
);
CREATE TABLE IF NOT EXISTS season_athletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_number TEXT NOT NULL UNIQUE,
    athlete_name TEXT NOT NULL,
    school TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    province TEXT NOT NULL DEFAULT '',
    team TEXT NOT NULL DEFAULT '',
    affiliated INTEGER NOT NULL DEFAULT 0 CHECK(affiliated IN (0, 1))
);
CREATE TABLE IF NOT EXISTS season_results (
    event_id INTEGER NOT NULL REFERENCES season_events(id) ON DELETE CASCADE,
    athlete_id INTEGER NOT NULL REFERENCES season_athletes(id),
    athlete_name TEXT NOT NULL,
    category TEXT NOT NULL,
    position TEXT NOT NULL,
    run_time TEXT NOT NULL,
    running_points TEXT NOT NULL,
    swim_time TEXT NOT NULL,
    swimming_points TEXT NOT NULL,
    bonus_points TEXT NOT NULL,
    total_points TEXT NOT NULL,
    status TEXT NOT NULL,
    school TEXT NOT NULL,
    province TEXT NOT NULL,
    team TEXT NOT NULL,
    annotations TEXT NOT NULL,
    PRIMARY KEY(event_id, athlete_id)
);
CREATE TABLE IF NOT EXISTS season_awards (
    event_id INTEGER NOT NULL,
    athlete_id INTEGER NOT NULL,
    award_type TEXT NOT NULL CHECK(award_type IN ('Runner', 'Swimmer', 'Overall Athlete')),
    placing INTEGER NOT NULL CHECK(placing BETWEEN 1 AND 3),
    PRIMARY KEY(event_id, athlete_id, award_type, placing),
    FOREIGN KEY(event_id, athlete_id) REFERENCES season_results(event_id, athlete_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS season_results_athlete ON season_results(athlete_id);
CREATE INDEX IF NOT EXISTS season_awards_athlete ON season_awards(athlete_id);
CREATE TABLE IF NOT EXISTS season_record_benchmarks (
    category_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    athlete_number TEXT NOT NULL,
    athlete_name TEXT NOT NULL DEFAULT '',
    total_points TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
"""


def season_database_path(base_dir: str | Path, environ=None) -> Path:
    """Never silently fall back when a configured database cannot be used.

DATABASE_URL currently accepts persistent sqlite:/// URLs only. A future
PostgreSQL implementation belongs here and in season_repository, not in UI.
"""
    environ = os.environ if environ is None else environ
    url = environ.get("DATABASE_URL", "").strip()
    configured = environ.get("SEASON_DATABASE_PATH", "").strip()
    if url:
        if not url.startswith("sqlite:///"):
            raise ValueError("Season Results Database V1 supports SQLite DATABASE_URL values only. PostgreSQL requires a future database adapter; no local fallback was opened.")
        configured = unquote(url[len("sqlite:///"):])
        if "?" in configured or "#" in configured:
            raise ValueError("Use a plain persistent SQLite file URL without query options.")
    if configured in {":memory:", "file::memory:"} or (url and not configured):
        raise ValueError("Season results require a persistent SQLite file.")
    path = Path(configured).expanduser() if configured else Path("data/season_results.sqlite")
    if not path.is_absolute():
        path = Path(base_dir) / path
    return path.resolve()


def init_season_db(db_path: str | Path) -> None:
    path = Path(db_path)
    if str(db_path) == ":memory:":
        raise ValueError("Season results require a persistent SQLite file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with get_conn(path) as conn:
        conn.executescript(SCHEMA)
