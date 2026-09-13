"""Multi-season history in the existing configured SQLite database."""
from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path
from urllib.parse import unquote

from .db import get_conn
from .migrations import backup_database, execute_schema

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
    season_year INTEGER CHECK(season_year BETWEEN 1900 AND 9999),
    UNIQUE(identity, event_date, competition_type, season_year)
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
    run_distance INTEGER CHECK(run_distance > 0),
    swim_distance INTEGER CHECK(swim_distance > 0),
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
CREATE TABLE IF NOT EXISTS athlete_seasons (
    athlete_id INTEGER NOT NULL REFERENCES season_athletes(id) ON DELETE CASCADE,
    season_year INTEGER NOT NULL CHECK(season_year BETWEEN 1900 AND 9999),
    category TEXT NOT NULL,
    PRIMARY KEY(athlete_id, season_year)
);
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
    path = path.resolve()
    # Inspect before using the normal connection, which enables WAL mode.
    import sqlite3
    legacy = False
    if path.exists() and path.stat().st_size:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as reader:
            columns = {r[1] for r in reader.execute("PRAGMA table_info(season_events)")}
            legacy = bool(columns) and ("season_year" not in columns or "workflow_key" not in columns)
        if legacy:
            backup_database(path)
    with get_conn(path) as conn:
        # Rebuild only the parent table to replace its old uniqueness constraint.
        # Keep child references and IDs intact; verify them before committing.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(season_events)")}
        if columns and "season_year" not in columns:
            sequence = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='season_events'").fetchone()
            definition = SCHEMA.split("CREATE TABLE IF NOT EXISTS season_events (", 1)[1].split(";", 1)[0]
            conn.execute("CREATE TABLE season_events_new (" + definition)
            conn.execute("""INSERT INTO season_events_new
                (id, identity, name, event_date, competition_type, source_filename, imported_at)
                SELECT id, identity, name, event_date, competition_type, source_filename, imported_at
                FROM season_events""")
            conn.execute("DROP TABLE season_events")
            conn.execute("ALTER TABLE season_events_new RENAME TO season_events")
            if sequence:
                conn.execute("""INSERT INTO sqlite_sequence(name, seq)
                    SELECT 'season_events', ? WHERE NOT EXISTS
                    (SELECT 1 FROM sqlite_sequence WHERE name='season_events')""", (sequence[0],))
                conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='season_events'", (sequence[0],))
            for discipline in ("run", "swim"):
                conn.execute(f"ALTER TABLE season_results ADD COLUMN {discipline}_distance INTEGER CHECK({discipline}_distance > 0)")
        execute_schema(conn, SCHEMA)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(season_events)")}
        if "workflow_key" not in columns:
            conn.execute("ALTER TABLE season_events ADD COLUMN workflow_key TEXT")
            conn.execute("ALTER TABLE season_events ADD COLUMN result_source TEXT NOT NULL DEFAULT 'published'")
            from services.competition import infer_season, distances
            for row in conn.execute("SELECT id,event_date FROM season_events WHERE season_year IS NULL").fetchall():
                try:
                    conn.execute("UPDATE season_events SET season_year=? WHERE id=?", (infer_season(row["event_date"]),row["id"]))
                except (ValueError, sqlite3.IntegrityError):
                    pass
            for row in conn.execute("SELECT event_id,athlete_id,category,run_distance,swim_distance FROM season_results").fetchall():
                run, swim = distances(row["category"])
                conn.execute("""UPDATE season_results SET run_distance=COALESCE(run_distance,?),
                    swim_distance=COALESCE(swim_distance,?) WHERE event_id=? AND athlete_id=?""",
                    (run,swim,row["event_id"],row["athlete_id"]))
            from .season_repository import _refresh_categories
            for row in conn.execute("SELECT DISTINCT season_year FROM season_events WHERE season_year IS NOT NULL").fetchall():
                _refresh_categories(conn, row[0])
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS history_workflow ON season_events(workflow_key) WHERE workflow_key IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS season_events_year ON season_events(season_year, id)")
        # SQLite UNIQUE permits multiple NULL values; legacy imports must still deduplicate.
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS season_events_unassigned
            ON season_events(identity, event_date, competition_type) WHERE season_year IS NULL""")
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Season migration found broken result links; migration rolled back.")
