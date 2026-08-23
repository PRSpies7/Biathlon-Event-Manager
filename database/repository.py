from __future__ import annotations

import json
from typing import Any, Iterable

from .db import get_conn, audit


def _touch_event(conn, event_id: int) -> None:
    conn.execute("UPDATE events SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))


def create_event(db_path: str, name: str, host_team: str, start_date: str, course: str, pool_lanes: int) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO events(name, host_team, start_date, course, pool_lanes) VALUES (?, ?, ?, ?, ?)",
            (name, host_team, start_date, course, pool_lanes),
        )
        event_id = int(cur.lastrowid)
    audit(db_path, event_id, "EVENT_CREATED", name)
    return event_id


def get_event(db_path: str, event_id: int):
    with get_conn(db_path) as conn:
        return conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()


def get_events(db_path: str) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY datetime(updated_at) DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def update_event(db_path: str, event_id: int, **fields: Any) -> None:
    allowed = {"name", "host_team", "start_date", "course", "pool_lanes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    cols, vals = [], []
    for key, value in updates.items():
        cols.append(f"{key} = ?")
        vals.append(value)
    cols.append("updated_at = CURRENT_TIMESTAMP")
    vals.append(event_id)
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE events SET {', '.join(cols)} WHERE id = ?", vals)


def replace_athletes(db_path: str, event_id: int, athletes: Iterable[dict[str, Any]]) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM athletes WHERE event_id = ?", (event_id,))
        rows = list(athletes)
        conn.executemany(
            """
            INSERT INTO athletes(
                event_id, sort_order, athlete_number, athlete_name, group_name,
                running_heat, running_lane, swimming_heat, swimming_lane
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (event_id, r["sort_order"], r["athlete_number"], r["athlete_name"], r.get("group_name"),
                 r.get("running_heat"), r.get("running_lane"), r.get("swimming_heat"), r.get("swimming_lane"))
                for r in rows
            ],
        )
        _touch_event(conn, event_id)
    audit(db_path, event_id, "MASTER_DATASET_CREATED", f"athletes={len(rows)}")


def get_athletes(db_path: str, event_id: int) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM athletes WHERE event_id = ? ORDER BY sort_order", (event_id,)).fetchall()]


def get_running_heats(db_path: str, event_id: int) -> list[int]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT running_heat FROM athletes WHERE event_id = ? AND running_heat IS NOT NULL ORDER BY running_heat", (event_id,)).fetchall()
    return [int(r[0]) for r in rows]


def get_swimming_heats(db_path: str, event_id: int) -> list[int]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT swimming_heat FROM athletes WHERE event_id = ? AND swimming_heat IS NOT NULL ORDER BY swimming_heat", (event_id,)).fetchall()
    return [int(r[0]) for r in rows]


def save_run_positions(db_path: str, event_id: int, heat_numbers: list[int], positions: dict[str, int | None]) -> None:
    group_key = "+".join(str(x) for x in sorted(heat_numbers))
    with get_conn(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO run_groups(event_id, group_key, heat_numbers, saved_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                     (event_id, group_key, json.dumps(sorted(heat_numbers))))
        for athlete_number, position in positions.items():
            conn.execute("UPDATE athletes SET run_group_key = ?, run_position = ? WHERE event_id = ? AND athlete_number = ?",
                         (group_key, position, event_id, athlete_number))
        _touch_event(conn, event_id)
    audit(db_path, event_id, "RUN_POSITIONS_SAVED", f"group={group_key}")


def update_run_times(db_path: str, event_id: int, results: dict[str, str]) -> None:
    with get_conn(db_path) as conn:
        for athlete_number, runtime in results.items():
            conn.execute("""UPDATE athletes SET run_time_imported = ?, run_time = CASE WHEN run_time_manual = 1 THEN run_time ELSE ? END WHERE event_id = ? AND athlete_number = ?""",
                         (runtime, runtime, event_id, athlete_number))
        _touch_event(conn, event_id)
    audit(db_path, event_id, "RUN_RESULTS_PROCESSED", f"records={len(results)}")


def update_swim_times(db_path: str, event_id: int, results: dict[str, str | None]) -> None:
    with get_conn(db_path) as conn:
        for athlete_number, swimtime in results.items():
            conn.execute("""UPDATE athletes SET swim_time_imported = ?, swim_time = CASE WHEN swim_time_manual = 1 THEN swim_time ELSE ? END WHERE event_id = ? AND athlete_number = ?""",
                         (swimtime, swimtime, event_id, athlete_number))
        _touch_event(conn, event_id)
    audit(db_path, event_id, "SWIM_RESULTS_PROCESSED", f"records={len(results)}")


def update_manual_time(db_path: str, event_id: int, athlete_number: str, field: str, value: str | None) -> None:
    if field not in {"run_time", "swim_time"}:
        raise ValueError("Invalid time field")
    flag = f"{field}_manual"
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE athletes SET {field} = ?, {flag} = 1 WHERE event_id = ? AND athlete_number = ?",
                     (value, event_id, athlete_number))
        _touch_event(conn, event_id)


def clear_results(db_path: str, event_id: int) -> None:
    with get_conn(db_path) as conn:
        conn.execute("""UPDATE athletes SET run_time = NULL, swim_time = NULL, run_time_imported = NULL, swim_time_imported = NULL, run_time_manual = 0, swim_time_manual = 0 WHERE event_id = ?""", (event_id,))
        _touch_event(conn, event_id)
    audit(db_path, event_id, "PHASE4_RESULTS_RESET", "Cleared imported and manually entered times")


def get_run_groups(db_path: str, event_id: int) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM run_groups WHERE event_id = ? ORDER BY id", (event_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["heat_numbers"] = json.loads(d["heat_numbers"])
        out.append(d)
    return out
