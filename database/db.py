from __future__ import annotations

import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path
from typing import Iterator
from .migrations import backup_database, execute_schema

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    host_team TEXT NOT NULL,
    start_date TEXT NOT NULL,
    course TEXT NOT NULL DEFAULT 'LCM',
    pool_lanes INTEGER NOT NULL DEFAULT 8,
    meet_type TEXT NOT NULL DEFAULT 'Local',
    season_year INTEGER CHECK(season_year BETWEEN 1900 AND 9999),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS athletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL,
    athlete_number TEXT NOT NULL,
    athlete_name TEXT NOT NULL,
    group_name TEXT,
    province TEXT,
    running_heat INTEGER,
    running_lane INTEGER,
    swimming_heat INTEGER,
    swimming_lane INTEGER,
    run_group_key TEXT,
    run_position INTEGER,
    run_time TEXT,
    swim_time TEXT,
    run_time_imported TEXT,
    swim_time_imported TEXT,
    run_time_manual INTEGER NOT NULL DEFAULT 0,
    swim_time_manual INTEGER NOT NULL DEFAULT 0,
    UNIQUE(event_id, athlete_number),
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS run_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    group_key TEXT NOT NULL,
    heat_numbers TEXT NOT NULL,
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, group_key),
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);
"""

HEAT_EVENT_COLUMNS = {
    "heat_source": "TEXT NOT NULL DEFAULT 'imported'",
    "heat_status": "TEXT NOT NULL DEFAULT 'approved'",
    "heat_revision": "INTEGER NOT NULL DEFAULT 0",
    "approved_revision": "INTEGER DEFAULT 0",
    "exports_revision": "INTEGER",
    "run_positions": "TEXT NOT NULL DEFAULT '[1,2,3,4,5,6,7,8,9,10,11,12]'",
    "history_key": "TEXT",
}
HEAT_ATHLETE_COLUMNS = {
    "history_athlete_id": "INTEGER", "gender": "TEXT", "run_distance": "INTEGER", "swim_distance": "INTEGER",
    "run_entered": "INTEGER", "swim_entered": "INTEGER",
    "run_seed": "INTEGER", "swim_seed": "INTEGER",
    "run_seed_source": "TEXT", "swim_seed_source": "TEXT",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: str | Path) -> None:
    path = Path(db_path).resolve()
    if path.exists() and path.stat().st_size:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as reader:
            columns = {r[1] for r in reader.execute("PRAGMA table_info(events)")}
        if columns and ("season_year" not in columns or any(c not in columns for c in HEAT_EVENT_COLUMNS)):
            backup_database(path)
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        execute_schema(conn, SCHEMA)
        # V1.1 migration for databases created by V1.0.
        event_columns = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
        if "meet_type" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN meet_type TEXT NOT NULL DEFAULT 'Local'")
        if "season_year" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN season_year INTEGER CHECK(season_year BETWEEN 1900 AND 9999)")

        columns = {row[1] for row in conn.execute("PRAGMA table_info(athletes)").fetchall()}
        migrations = {
            "run_time_imported": "ALTER TABLE athletes ADD COLUMN run_time_imported TEXT",
            "swim_time_imported": "ALTER TABLE athletes ADD COLUMN swim_time_imported TEXT",
            "run_time_manual": "ALTER TABLE athletes ADD COLUMN run_time_manual INTEGER NOT NULL DEFAULT 0",
            "swim_time_manual": "ALTER TABLE athletes ADD COLUMN swim_time_manual INTEGER NOT NULL DEFAULT 0",
            "province": "ALTER TABLE athletes ADD COLUMN province TEXT",
        }
        for column, sql in migrations.items():
            if column not in columns:
                conn.execute(sql)
        for column, definition in HEAT_EVENT_COLUMNS.items():
            if column not in event_columns:
                conn.execute(f"ALTER TABLE events ADD COLUMN {column} {definition}")
        for column, definition in HEAT_ATHLETE_COLUMNS.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE athletes ADD COLUMN {column} {definition}")
        from uuid import uuid4
        for row in conn.execute("SELECT id FROM events WHERE history_key IS NULL").fetchall():
            conn.execute("UPDATE events SET history_key=? WHERE id=?",(str(uuid4()),row[0]))
        if "heat_revision" not in event_columns:
            from services.competition import infer_season, distances, gender_for_group
            for row in conn.execute("SELECT id,start_date FROM events WHERE season_year IS NULL").fetchall():
                try:
                    conn.execute("UPDATE events SET season_year=? WHERE id=?", (infer_season(row["start_date"]), row["id"]))
                except ValueError:
                    pass
            for row in conn.execute("SELECT * FROM athletes").fetchall():
                run, swim = distances(row["group_name"])
                conn.execute("""UPDATE athletes SET run_distance=?,swim_distance=?,gender=?,
                    run_entered=?,swim_entered=? WHERE id=?""", (run, swim, gender_for_group(row["group_name"]),
                    int(row["running_heat"] is not None), int(row["swimming_heat"] is not None), row["id"]))
        conn.execute("""CREATE TABLE IF NOT EXISTS event_outputs (
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL, filename TEXT NOT NULL, mime TEXT NOT NULL,
            content BLOB NOT NULL, PRIMARY KEY(event_id,filename))""")
        assignment_columns = ["running_heat", "running_lane", "swimming_heat", "swimming_lane",
            "athlete_number", "athlete_name", "group_name", "province", *HEAT_ATHLETE_COLUMNS]
        differs = " OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in assignment_columns)
        for action, reference, condition in (("INSERT", "NEW", ""), ("DELETE", "OLD", ""),
                ("UPDATE OF " + ",".join(assignment_columns), "NEW", "WHEN " + differs)):
            name = action.split()[0].lower()
            conn.execute(f"""CREATE TRIGGER IF NOT EXISTS heat_assignments_{name}
                AFTER {action} ON athletes {condition} BEGIN
                UPDATE events SET heat_revision=heat_revision+1,approved_revision=NULL,exports_revision=NULL,
                    heat_status=CASE WHEN heat_status='draft' THEN 'draft' ELSE 'stale' END
                WHERE id={reference}.event_id; END""")
        metadata = ["name", "host_team", "start_date", "course", "pool_lanes", "meet_type", "season_year", "run_positions"]
        differs = " OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in metadata)
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS heat_metadata_changed
            AFTER UPDATE OF {','.join(metadata)} ON events WHEN {differs} BEGIN
            UPDATE events SET heat_revision=heat_revision+1,approved_revision=NULL,exports_revision=NULL,
                heat_status=CASE WHEN heat_status='draft' THEN 'draft' ELSE 'stale' END WHERE id=NEW.id; END""")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_conn(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(db_path: str | Path, event_id: int, action: str, details: str = "") -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO audit_log(event_id, action, details) VALUES (?, ?, ?)",
            (event_id, action, details),
        )
