from __future__ import annotations

import json
from uuid import uuid4
from typing import Any, Iterable

from .db import get_conn, audit, HEAT_ATHLETE_COLUMNS
from .migrations import validate_season


def _touch_event(conn, event_id: int) -> None:
    conn.execute("UPDATE events SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (event_id,))


def create_event(
    db_path: str,
    name: str,
    host_team: str,
    start_date: str,
    course: str,
    pool_lanes: int,
    meet_type: str = "Local",
    season_year: int | None = None,
    heat_source: str = "imported",
    run_positions: list[int] | None = None,
) -> int:
    if heat_source not in {"imported", "generated"}:
        raise ValueError("Unknown heat source.")
    if season_year is None:
        from services.competition import infer_season
        season_year = infer_season(start_date)
    validate_season(season_year)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO events(name, host_team, start_date, course, pool_lanes, meet_type, season_year,heat_source,heat_status,run_positions,history_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, host_team, start_date, course, pool_lanes, meet_type, season_year, heat_source,
             "draft" if heat_source == "generated" else "approved", json.dumps(run_positions or list(range(1,13))),str(uuid4())),
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


def delete_all_events(db_path: str) -> int:
    """Delete all saved event sessions and their cascading related records."""
    with get_conn(db_path) as conn:
        event_count = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        conn.execute("DELETE FROM events")
    return event_count


def update_event(db_path: str, event_id: int, **fields: Any) -> None:
    allowed = {"name", "host_team", "start_date", "course", "pool_lanes", "meet_type", "season_year", "run_positions"}
    if "season_year" in fields:
        validate_season(fields["season_year"])
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
                event_id, sort_order, athlete_number, athlete_name, group_name, province,
                running_heat, running_lane, swimming_heat, swimming_lane
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (event_id, r["sort_order"], r["athlete_number"], r["athlete_name"], r.get("group_name"), r.get("province"),
                 r.get("running_heat"), r.get("running_lane"), r.get("swimming_heat"), r.get("swimming_lane"))
                for r in rows
            ],
        )
        extra = list(HEAT_ATHLETE_COLUMNS)
        for r in rows:
            conn.execute(f"UPDATE athletes SET {','.join(c+'=?' for c in extra)} WHERE event_id=? AND athlete_number=?",
                         (*[r.get(c) for c in extra], event_id, r["athlete_number"]))
        _touch_event(conn, event_id)
    audit(db_path, event_id, "MASTER_DATASET_CREATED", f"athletes={len(rows)}")


def get_athletes(db_path: str, event_id: int) -> list[dict[str, Any]]:
    with get_conn(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM athletes WHERE event_id = ? ORDER BY sort_order", (event_id,)).fetchall()]


def save_heat_assignments(db_path, event_id, rows, expected_revision, *, generation_profile=None):
    """Save manual/generator output without touching captured finish positions or times."""
    fields = ["running_heat","running_lane","swimming_heat","swimming_lane","group_name",*HEAT_ATHLETE_COLUMNS]
    if generation_profile is not None:
        from services.competition import GENERATION_PROFILES
        if generation_profile not in GENERATION_PROFILES:
            raise ValueError("Select a valid heat generation profile.")
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if event is None or event["heat_revision"] != expected_revision:
            raise ValueError("The event changed in another session. Reload before editing heats.")
        existing = {r[0] for r in conn.execute("SELECT athlete_number FROM athletes WHERE event_id=?", (event_id,))}
        if len(rows) != len(existing) or {r["athlete_number"] for r in rows} != existing:
            raise ValueError("Heat edits must retain the event's complete athlete roster.")
        for row in rows:
            conn.execute(f"UPDATE athletes SET {','.join(f+'=?' for f in fields)} WHERE event_id=? AND athlete_number=?",
                (*[row.get(f) for f in fields],event_id,row["athlete_number"]))
        if generation_profile is not None:
            # Also invalidate a previous approval when regeneration happens to
            # produce identical assignments; record provenance atomically.
            conn.execute("UPDATE events SET heat_revision=heat_revision+1,approved_revision=NULL,exports_revision=NULL,heat_status=CASE WHEN heat_status='draft' THEN 'draft' ELSE 'stale' END WHERE id=?",(event_id,))
            revision = conn.execute("SELECT heat_revision FROM events WHERE id=?",(event_id,)).fetchone()[0]
            metadata = json.dumps({"profile":generation_profile,"revision":revision})
            conn.execute("UPDATE events SET generation_metadata=? WHERE id=?",(metadata,event_id))
            conn.execute("INSERT INTO audit_log(event_id,action,details) VALUES (?,?,?)",(event_id,"HEATS_GENERATED",metadata))
        _touch_event(conn,event_id)


def save_review_roster(db_path, event_id, rows, expected_revision, *, added=(), removed=()):
    """Atomically save explicit event-only roster changes and reviewed assignments.

    Existing timing/capture fields and historical results are never overwritten.
    Removed event rows are retained in the audit details for traceability.
    """
    from services.seeding import number_key
    added, removed = set(added), set(removed)
    fields = ["running_heat", "running_lane", "swimming_heat", "swimming_lane", "group_name", *HEAT_ATHLETE_COLUMNS]
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        event = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if event is None or event["heat_revision"] != expected_revision:
            raise ValueError("The event changed in another session. Reload before saving.")
        existing = {r["athlete_number"]: dict(r) for r in conn.execute("SELECT * FROM athletes WHERE event_id=?", (event_id,))}
        numbers = [r["athlete_number"] for r in rows]
        if (added & set(existing) or not removed <= set(existing) or
                set(numbers) != (set(existing)-removed) | added or len(numbers) != len(set(numbers))):
            raise ValueError("The roster change must explicitly identify every addition and removal.")
        if len({number_key(n) for n in numbers}) != len(numbers):
            raise ValueError("Athlete numbers must be unique within this event.")
        for number in removed:
            conn.execute("INSERT INTO audit_log(event_id,action,details) VALUES (?,?,?)",
                         (event_id, "EVENT_ATHLETE_REMOVED", json.dumps(existing[number])))
            conn.execute("DELETE FROM athletes WHERE event_id=? AND athlete_number=?", (event_id, number))
        for row in rows:
            if row["athlete_number"] in added:
                conn.execute("INSERT INTO athletes(event_id,sort_order,athlete_number,athlete_name,province) VALUES (?,?,?,?,?)",
                             (event_id,row["sort_order"],row["athlete_number"],row["athlete_name"],row.get("province")))
            conn.execute(f"UPDATE athletes SET {','.join(f+'=?' for f in fields)} WHERE event_id=? AND athlete_number=?",
                         (*[row.get(f) for f in fields],event_id,row["athlete_number"]))
        _touch_event(conn,event_id)


def approve_heats(db_path,event_id,expected_revision):
    from services.heats import validate_heats
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        event = conn.execute("SELECT * FROM events WHERE id=?",(event_id,)).fetchone()
        if event is None or event["heat_revision"] != expected_revision:
            raise ValueError("Heat assignments changed. Reload and review before approving.")
        rows = [dict(r) for r in conn.execute("SELECT * FROM athletes WHERE event_id=?",(event_id,))]
        errors,warnings = validate_heats(rows,dict(event))
        if errors:
            raise ValueError("\n".join(errors))
        conn.execute("UPDATE events SET heat_status='approved',approved_revision=heat_revision WHERE id=?",(event_id,))
    return warnings


def get_running_heats(db_path: str, event_id: int) -> list[int]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT running_heat FROM athletes WHERE event_id = ? AND running_heat IS NOT NULL ORDER BY running_heat", (event_id,)).fetchall()
        group_rows = conn.execute(
            "SELECT heat_numbers FROM run_groups WHERE event_id = ?", (event_id,)
        ).fetchall()
    heats = {int(r[0]) for r in rows}
    for row in group_rows:
        heats.update(int(number) for number in json.loads(row[0]))
    return sorted(heats)


def get_swimming_heats(db_path: str, event_id: int) -> list[int]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT swimming_heat FROM athletes WHERE event_id = ? AND swimming_heat IS NOT NULL ORDER BY swimming_heat", (event_id,)).fetchall()
    return [int(r[0]) for r in rows]


def assign_athlete_to_run_heat(db_path: str, event_id: int, athlete_number: str, running_heat: int) -> bool:
    """Move an existing athlete into a selected run heat without creating a new record.

    Returns ``False`` when the athlete is already in that heat. A move clears the
    athlete's old position/group mapping, which belongs to the previous heat.
    """
    athlete_number = str(athlete_number).strip()
    with get_conn(db_path) as conn:
        athlete = conn.execute(
            "SELECT running_heat FROM athletes WHERE event_id = ? AND athlete_number = ?",
            (event_id, athlete_number),
        ).fetchone()
        if athlete is None:
            raise ValueError(f"Athlete {athlete_number} was not found in this event.")
        if athlete["running_heat"] == int(running_heat):
            return False
        conn.execute(
            """UPDATE athletes
               SET running_heat = ?, running_lane = NULL, run_group_key = NULL, run_position = NULL
               WHERE event_id = ? AND athlete_number = ?""",
            (int(running_heat), event_id, athlete_number),
        )
        _touch_event(conn, event_id)
    audit(db_path, event_id, "ATHLETE_RUN_HEAT_CHANGED", f"athlete={athlete_number}, heat={running_heat}")
    return True


def remove_athlete_from_run_heat(
    db_path: str,
    event_id: int,
    athlete_number: str,
    selected_heats: Iterable[int],
) -> bool:
    """Clear one athlete's run assignment without deleting the athlete record."""
    athlete_number = str(athlete_number).strip()
    allowed_heats = {int(heat) for heat in selected_heats}
    if not allowed_heats:
        raise ValueError("Select a run heat before removing an athlete.")

    with get_conn(db_path) as conn:
        athlete = conn.execute(
            "SELECT running_heat FROM athletes WHERE event_id = ? AND athlete_number = ?",
            (event_id, athlete_number),
        ).fetchone()
        if athlete is None:
            raise ValueError(f"Athlete {athlete_number} was not found in this event.")
        if athlete["running_heat"] is None:
            return False
        running_heat = int(athlete["running_heat"])
        if running_heat not in allowed_heats:
            raise ValueError(f"Athlete {athlete_number} is no longer assigned to the selected run heat.")

        # Keep an emptied heat available in Phase 2 navigation without adding a
        # new table or changing the schema. Existing combined groups already do this.
        group_rows = conn.execute(
            "SELECT heat_numbers FROM run_groups WHERE event_id = ?", (event_id,)
        ).fetchall()
        if not any(running_heat in {int(n) for n in json.loads(row[0])} for row in group_rows):
            group_key = str(running_heat)
            conn.execute(
                "INSERT OR IGNORE INTO run_groups(event_id, group_key, heat_numbers, saved_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, group_key, json.dumps([running_heat])),
            )

        conn.execute(
            """UPDATE athletes
               SET running_heat = NULL, running_lane = NULL,
                   run_group_key = NULL, run_position = NULL
               WHERE event_id = ? AND athlete_number = ?""",
            (event_id, athlete_number),
        )
        _touch_event(conn, event_id)
    audit(db_path, event_id, "ATHLETE_REMOVED_FROM_RUN_HEAT", f"athlete={athlete_number}, heat={running_heat}")
    return True


def add_athlete_to_run_heat(
    db_path: str,
    event_id: int,
    athlete_number: str,
    athlete_name: str,
    running_heat: int,
) -> None:
    """Create one numbered athlete and place them in a run heat.

    The event-scoped unique constraint remains the final duplicate safeguard.
    New Phase 2 athletes have no inferred swim assignment or age group.
    """
    athlete_number = str(athlete_number).strip()
    athlete_name = str(athlete_name).strip()
    if not athlete_number:
        raise ValueError("A new athlete must have an athlete number.")
    if not athlete_name:
        raise ValueError("Enter the athlete name to add this new athlete.")

    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM athletes WHERE event_id = ? AND athlete_number = ?",
            (event_id, athlete_number),
        ).fetchone()
        if existing:
            raise ValueError(f"Athlete number {athlete_number} already exists in this event.")
        next_sort_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM athletes WHERE event_id = ?",
            (event_id,),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO athletes(
                event_id, sort_order, athlete_number, athlete_name, group_name,
                running_heat, running_lane, swimming_heat, swimming_lane
            ) VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL)""",
            (event_id, next_sort_order, athlete_number, athlete_name, int(running_heat)),
        )
        _touch_event(conn, event_id)
    audit(db_path, event_id, "ATHLETE_ADDED_TO_RUN_HEAT", f"athlete={athlete_number}, heat={running_heat}")


def restore_run_position_mappings(
    db_path: str,
    event_id: int,
    mappings: list[dict[str, Any]],
) -> int:
    """Replace Phase 2 group/position mappings from a Run Position Export.

    Validation occurs before any mutation so a malformed export cannot leave a
    partially restored event. Athlete numbers are the only identity used.
    """
    if not mappings:
        raise ValueError("The Run Position Export does not contain any mappings.")

    with get_conn(db_path) as conn:
        known_athletes = {
            str(row[0]) for row in conn.execute(
                "SELECT athlete_number FROM athletes WHERE event_id = ?", (event_id,)
            ).fetchall()
        }
        known_heats = {
            int(row[0]) for row in conn.execute(
                "SELECT DISTINCT running_heat FROM athletes WHERE event_id = ? AND running_heat IS NOT NULL",
                (event_id,),
            ).fetchall()
        }
        seen_athletes: set[str] = set()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for mapping in mappings:
            athlete_number = str(mapping.get("athlete_number", "")).strip()
            heat_numbers = sorted({int(n) for n in mapping.get("heat_numbers", [])})
            position = mapping.get("run_position")
            if not athlete_number:
                raise ValueError("The Run Position Export contains a blank athlete number.")
            if athlete_number not in known_athletes:
                raise ValueError(f"Athlete number {athlete_number} is not in this event.")
            if athlete_number in seen_athletes:
                raise ValueError(f"Athlete number {athlete_number} appears more than once in the export.")
            if not heat_numbers or any(h not in known_heats for h in heat_numbers):
                raise ValueError(f"Invalid heat mapping for athlete number {athlete_number}.")
            if position is not None and (not isinstance(position, int) or position < 1):
                raise ValueError(f"Invalid run position for athlete number {athlete_number}.")
            seen_athletes.add(athlete_number)
            group_key = "+".join(str(h) for h in heat_numbers)
            grouped.setdefault(group_key, []).append({
                "athlete_number": athlete_number,
                "heat_numbers": heat_numbers,
                "run_position": position,
            })

        for group_key, rows in grouped.items():
            positions = [r["run_position"] for r in rows if r["run_position"] is not None]
            if len(positions) != len(set(positions)):
                raise ValueError(f"Run Position Export has duplicate positions in Heat {group_key.replace('+', ' + ')}.")

        conn.execute(
            "UPDATE athletes SET run_group_key = NULL, run_position = NULL WHERE event_id = ?",
            (event_id,),
        )
        conn.execute("DELETE FROM run_groups WHERE event_id = ?", (event_id,))
        for group_key, rows in grouped.items():
            heat_numbers = rows[0]["heat_numbers"]
            conn.execute(
                "INSERT INTO run_groups(event_id, group_key, heat_numbers, saved_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (event_id, group_key, json.dumps(heat_numbers)),
            )
            for row in rows:
                conn.execute(
                    """UPDATE athletes
                       SET run_group_key = ?, run_position = ?,
                           running_heat = CASE WHEN ? = 1 THEN ? ELSE running_heat END
                       WHERE event_id = ? AND athlete_number = ?""",
                    (
                        group_key,
                        row["run_position"],
                        len(heat_numbers),
                        heat_numbers[0],
                        event_id,
                        row["athlete_number"],
                    ),
                )
        _touch_event(conn, event_id)
    audit(db_path, event_id, "RUN_POSITIONS_RESTORED", f"records={len(mappings)}")
    return len(mappings)


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
