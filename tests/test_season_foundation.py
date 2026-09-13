"""Focused multi-season storage and legacy migration coverage."""
from dataclasses import replace
from datetime import date
import sqlite3
from pathlib import Path

import pytest

from database.db import init_db, get_conn
from database.repository import create_event, get_event, update_event
from database.season_db import init_season_db
from database.season_repository import (
    assign_event_season, available_seasons, historical_performances,
    reset_season_database, season_snapshot, store_event,
)
from parsers.season_results.models import Award, LEAGUE, NormalizedEvent, Result


def event(year=2026, category="U/11 GIRLS", **changes):
    value = NormalizedEvent("League", date(2025, 11, 1), LEAGUE, "results.xlsx",
        [Result("101", "Alex Example", category, run_time="01:20.00", swim_time="00:40.00",
                run_distance=400, swim_distance=50)],
        [Award("101", "Alex Example", "Runner", 1)], season_year=year)
    return replace(value, **changes)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "history.sqlite"
    init_season_db(path)
    return path


def test_seasons_preserve_identity_and_competed_category(db):
    newer = event(2027, "U/13 GIRLS")
    store_event(db, newer)
    store_event(db, event())  # Older season imported last, with the same date/name.
    assert available_seasons(db) == [2027, 2026]
    old, new = season_snapshot(db, 2026), season_snapshot(db, 2027)
    assert old["athletes"][0]["id"] == new["athletes"][0]["id"]
    assert old["athletes"][0]["category"] == "U/11 GIRLS"
    assert new["athletes"][0]["category"] == "U/13 GIRLS"
    assert len(old["events"]) == len(old["results"]) == len(old["awards"]) == 1
    assert old["athletes"][0]["events_attended"] == 1
    assert new["results"][0]["season_year"] == 2027
    assert new["events"][0]["event_date"].startswith("2025")
    assert season_snapshot(db)["athletes"][0]["category"] == "U/13 GIRLS"


def test_category_projection_handles_overwrite_and_season_correction(db):
    first = store_event(db, event())
    later = event(category="U/13 GIRLS", name="Later", event_date=date(2026, 2, 1))
    later_id = store_event(db, later)
    assert season_snapshot(db, 2026)["athletes"][0]["category"] == "U/13 GIRLS"
    store_event(db, replace(later, results=[Result("102", "Other Athlete", "U/15 GIRLS")], awards=[]), overwrite=True)
    rows = {a["athlete_number"]: a for a in season_snapshot(db, 2026)["athletes"]}
    assert rows["101"]["category"] == "U/11 GIRLS"
    assign_event_season(db, first, 2027)
    assert [a["athlete_number"] for a in season_snapshot(db, 2026)["athletes"]] == ["102"]
    assert season_snapshot(db, 2027)["events"][0]["id"] == first
    assert season_snapshot(db, 2026)["events"][0]["id"] == later_id


def test_history_is_distance_and_two_season_scoped(db):
    from services.season_results_service import import_event
    with pytest.raises(ValueError, match="Season"):
        import_event(db, event(None))
    for year in (2024, 2025, 2026, 2027, None):
        store_event(db, event(year))
    unknown = event(name="Unknown distances", results=[Result("101", "Alex Example", "SPECIAL NEEDS", run_time="00:10.00")], awards=[])
    store_event(db, unknown)
    athlete_id = season_snapshot(db, 2026)["athletes"][0]["id"]
    candidates = historical_performances(db, athlete_id, "run", 400, 2026)
    assert [r["season_year"] for r in candidates] == [2026, 2025, 2024]
    assert all(r["event_name"] == "League" and r["distance"] == 400 for r in candidates)
    assert historical_performances(db, athlete_id, "run", 800, 2026) == []
    assert len(historical_performances(db, athlete_id, "swim", 50, 2026)) == 3
    with pytest.raises(ValueError):
        historical_performances(db, athlete_id, "other", 400, 2026)


def test_reset_cannot_delete_other_seasons_or_shared_identity(db):
    store_event(db, event())
    store_event(db, event(2027))
    before = season_snapshot(db, 2027)
    with pytest.raises(ValueError, match="Select a Season"):
        reset_season_database(db)
    reset_season_database(db, 2026)
    assert season_snapshot(db, 2027) == before
    assert season_snapshot(db, 2026)["results"] == []


def test_legacy_migration_preserves_rows_and_backups_and_is_repeatable(tmp_path):
    path = tmp_path / "legacy.sqlite"
    schema = (Path(__file__).parent / "fixtures" / "legacy_season_schema.sql").read_text()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(schema)
        conn.execute("INSERT INTO season_events VALUES (7, 'league', 'League', '2025-11-01', ?, 'old.xlsx', 'saved')", (LEAGUE,))
        conn.execute("INSERT INTO season_athletes VALUES (3, '101', 'Alex Example', 'School', 'U/11 GIRLS', 'GN', 'GN', 1)")
        conn.execute("INSERT INTO season_results VALUES (7,3,'Alex Example','U/11 GIRLS','1','01:20.00','1000','00:40.00','1000','0','2000','','School','GN','GN','')")
        conn.execute("INSERT INTO season_awards VALUES (7,3,'Runner',1)")
        conn.execute("UPDATE sqlite_sequence SET seq=20 WHERE name='season_events'")
    init_season_db(path)
    first = season_snapshot(path)
    assert first["events"][0]["id"] == 7 and first["events"][0]["season_year"] == 2026
    assert first["results"][0]["run_distance"] == 400
    assert first["athletes"][0]["affiliated"] == 1
    assert len(first["awards"]) == 1
    backups = list(tmp_path.glob("*.before-seasons-*.sqlite"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert "season_year" not in {r[1] for r in conn.execute("PRAGMA table_info(season_events)")}
        assert conn.execute("SELECT COUNT(*) FROM season_results").fetchone()[0] == 1
    init_season_db(path)
    assert season_snapshot(path) == first
    assert list(tmp_path.glob("*.before-seasons-*.sqlite")) == backups
    assign_event_season(path, 7, 2026)
    assert season_snapshot(path, None)["events"] == []
    assert season_snapshot(path, 2026)["athletes"][0]["category"] == "U/11 GIRLS"
    with get_conn(path) as conn:
        assert list(conn.execute("PRAGMA foreign_key_check")) == []
        assert conn.execute("SELECT seq FROM sqlite_sequence WHERE name='season_events'").fetchone()[0] == 20
        conn.execute("DELETE FROM season_events WHERE id=7")
        assert conn.execute("SELECT COUNT(*) FROM season_results").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM season_awards").fetchone()[0] == 0


def test_operational_event_season_does_not_follow_date(tmp_path):
    path = tmp_path / "workflow.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            host_team TEXT NOT NULL, start_date TEXT NOT NULL,
            course TEXT NOT NULL DEFAULT 'LCM', pool_lanes INTEGER NOT NULL DEFAULT 8,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("INSERT INTO events(name,host_team,start_date) VALUES ('Legacy','GN','2025-11-01')")
    init_db(path)
    assert get_event(path, 1)["season_year"] == 2026
    assert len(list(tmp_path.glob("*.before-seasons-*.sqlite"))) == 1
    event_id = create_event(path, "League", "GN", "2025-11-01", "SCM", 6, season_year=2026)
    assert get_event(path, event_id)["season_year"] == 2026
    update_event(path, event_id, season_year=2027)
    assert get_event(path, event_id)["season_year"] == 2027
    with pytest.raises(ValueError):
        update_event(path, event_id, season_year=True)


def test_failed_migration_rolls_back_schema_and_preserves_data(tmp_path):
    path = tmp_path / "broken-links.sqlite"
    schema = (Path(__file__).parent / "fixtures" / "legacy_season_schema.sql").read_text()
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
        conn.execute("INSERT INTO season_awards VALUES (99,99,'Runner',1)")
    with pytest.raises(ValueError, match="rolled back"):
        init_season_db(path)
    with sqlite3.connect(path) as conn:
        assert "season_year" not in {r[1] for r in conn.execute("PRAGMA table_info(season_events)")}
        assert conn.execute("SELECT COUNT(*) FROM season_awards").fetchone()[0] == 1
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='season_events_new'").fetchall()
