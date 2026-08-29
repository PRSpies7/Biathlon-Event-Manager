from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from database.db import init_db
from database.repository import (
    create_event,
    delete_all_events,
    get_event,
    get_events,
    replace_athletes,
    save_run_positions,
)


class ResetSessionsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "sessions.sqlite"
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_saved_event(self, name: str, athlete_number: str) -> int:
        event_id = create_event(
            str(self.db_path),
            name,
            "Gauteng North Biathlon",
            "2026-08-29",
            "SCM",
            8,
        )
        replace_athletes(
            str(self.db_path),
            event_id,
            [
                {
                    "sort_order": 1,
                    "athlete_number": athlete_number,
                    "athlete_name": f"Athlete {athlete_number}",
                    "group_name": "U/11 GIRLS",
                    "running_heat": 1,
                    "running_lane": 1,
                    "swimming_heat": 1,
                    "swimming_lane": 1,
                }
            ],
        )
        save_run_positions(str(self.db_path), event_id, [1], {athlete_number: 1})
        return event_id

    def _table_counts(self) -> dict[str, int]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in ("events", "athletes", "run_groups", "audit_log")
            }

    def test_reset_deletes_events_and_all_cascading_event_records(self):
        first_id = self._create_saved_event("First saved session", "1001")
        second_id = self._create_saved_event("Second saved session", "1002")

        self.assertEqual(len(get_events(str(self.db_path))), 2)
        self.assertEqual(get_event(str(self.db_path), first_id)["name"], "First saved session")
        self.assertEqual(get_event(str(self.db_path), second_id)["name"], "Second saved session")
        self.assertTrue(all(count > 0 for count in self._table_counts().values()))

        self.assertEqual(delete_all_events(str(self.db_path)), 2)

        self.assertEqual(self._table_counts(), {"events": 0, "athletes": 0, "run_groups": 0, "audit_log": 0})
        self.assertEqual(get_events(str(self.db_path)), [])

    def test_database_schema_remains_usable_after_reset(self):
        self._create_saved_event("Old session", "1001")
        delete_all_events(str(self.db_path))

        with closing(sqlite3.connect(self.db_path)) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        self.assertTrue({"events", "athletes", "run_groups", "audit_log"}.issubset(tables))

        new_event_id = self._create_saved_event("New session", "2001")
        self.assertEqual(get_event(str(self.db_path), new_event_id)["name"], "New session")
        self.assertEqual([event["name"] for event in get_events(str(self.db_path))], ["New session"])


if __name__ == "__main__":
    unittest.main()
