"""Season storage operations. UI, parsers and exporters never issue SQL."""
from __future__ import annotations

from datetime import datetime, timezone

from .db import get_conn
from .migrations import validate_season
from parsers.season_results.models import NormalizedEvent
from parsers.season_records import validate_record_benchmarks


class EventAlreadyExists(ValueError):
    pass


def reset_season_database(db_path, season_year=None) -> None:
    """Clear only season data atomically, preserving schema and workflow sessions."""
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        validate_season(season_year)
        if season_year is not None:
            conn.execute("DELETE FROM season_events WHERE season_year=?", (season_year,))
            conn.execute("DELETE FROM athlete_seasons WHERE season_year=?", (season_year,))
            return
        if conn.execute("SELECT 1 FROM season_events WHERE season_year IS NOT NULL LIMIT 1").fetchone():
            raise ValueError("Select a Season to reset; other seasons and shared athlete identities must be preserved.")
        conn.execute("DELETE FROM season_events")  # Cascades results and awards.
        conn.execute("DELETE FROM season_athletes")
        conn.execute("DELETE FROM season_record_benchmarks")
        conn.execute("DELETE FROM season_record_templates")


def replace_record_benchmarks(db_path, records, source_filename, template_bytes=None):
    if template_bytes:
        from io import BytesIO
        from parsers.season_records import parse_record_benchmarks
        records = parse_record_benchmarks(BytesIO(template_bytes))
    else:
        records = validate_record_benchmarks(records)
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM season_record_benchmarks")
        conn.execute("DELETE FROM season_record_templates")
        if template_bytes:
            conn.execute("INSERT INTO season_record_templates VALUES (1, ?, ?)", (source_filename, template_bytes))
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        conn.executemany("""INSERT INTO season_record_benchmarks
            (category_key, category, athlete_number, athlete_name, total_points, source_filename, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(r["category_key"], r["category"], r["athlete_number"], r["athlete_name"], r["total_points"],
              source_filename, imported_at) for r in records])


def find_event(db_path, event: NormalizedEvent):
    if not event.event_date:
        return None
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM season_events WHERE identity=? AND event_date=? AND competition_type=? AND season_year IS ?",
            (event.identity, event.event_date.isoformat(), event.competition_type, event.season_year),
        ).fetchone()
    return dict(row) if row else None


def store_event(db_path, event: NormalizedEvent, *, overwrite: bool = False) -> int:
    from services.season_scope import gn_event
    event = gn_event(event)
    event.check_structure()
    with get_conn(db_path) as conn:
        # Serialize duplicate check + replacement, including concurrent browser imports.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT id FROM season_events WHERE identity=? AND event_date=? AND competition_type=? AND season_year IS ?",
            (event.identity, event.event_date.isoformat(), event.competition_type, event.season_year),
        ).fetchone()
        if existing and not overwrite:
            raise EventAlreadyExists("This event already exists. Overwrite the existing event results or skip this event?")
        imported_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        if existing:
            event_id = existing["id"]
            conn.execute("DELETE FROM season_results WHERE event_id=?", (event_id,))
            conn.execute("UPDATE season_events SET name=?, source_filename=?, imported_at=? WHERE id=?",
                         (event.name.strip(), event.source_filename, imported_at, event_id))
        else:
            event_id = conn.execute(
                "INSERT INTO season_events(identity, name, event_date, competition_type, source_filename, imported_at, season_year) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event.identity, event.name.strip(), event.event_date.isoformat(), event.competition_type, event.source_filename, imported_at, event.season_year),
            ).lastrowid
        affiliated_awards = {a.athlete_number for a in event.awards if a.affiliated}
        ids = {}
        for r in event.results:
            conn.execute("""
                INSERT INTO season_athletes(athlete_number, athlete_name, school, category, province, team, affiliated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(athlete_number) DO UPDATE SET
                    athlete_name=excluded.athlete_name,
                    school=COALESCE(NULLIF(excluded.school, ''), season_athletes.school),
                    province=COALESCE(NULLIF(excluded.province, ''), season_athletes.province),
                    team=COALESCE(NULLIF(excluded.team, ''), season_athletes.team),
                    affiliated=MAX(season_athletes.affiliated, excluded.affiliated)
            """, (r.athlete_number, r.athlete_name, r.school, r.category, r.province, r.team,
                  int(r.affiliated or r.athlete_number in affiliated_awards)))
            athlete_id = conn.execute("SELECT id FROM season_athletes WHERE athlete_number=?", (r.athlete_number,)).fetchone()["id"]
            ids[r.athlete_number] = athlete_id
            conn.execute("""
                INSERT INTO season_results(event_id, athlete_id, athlete_name, category, position,
                    run_time, running_points, swim_time, swimming_points, bonus_points, total_points,
                    status, school, province, team, annotations, run_distance, swim_distance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, athlete_id, r.athlete_name, r.category, r.position, r.run_time, r.running_points,
                  r.swim_time, r.swimming_points, r.bonus_points, r.total_points, r.status,
                  r.school, r.province, r.team, r.annotations, r.run_distance, r.swim_distance))
        for award in event.awards:
            conn.execute("INSERT INTO season_awards(event_id, athlete_id, award_type, placing) VALUES (?, ?, ?, ?)",
                         (event_id, ids[award.athlete_number], award.award_type, award.placing))
        if event.season_year is not None:
            _refresh_categories(conn, event.season_year)
    return event_id


def _refresh_categories(conn, season_year):
    """Project the latest competed category, regardless of import order.

    Result categories remain immutable snapshots. Rebuild also removes stale
    category memberships when an event overwrite removes an athlete.
    """
    conn.execute("DELETE FROM athlete_seasons WHERE season_year=?", (season_year,))
    conn.execute("""INSERT INTO athlete_seasons(athlete_id, season_year, category)
        SELECT athlete_id, season_year, category FROM (
            SELECT r.athlete_id, e.season_year, r.category,
                ROW_NUMBER() OVER (PARTITION BY r.athlete_id ORDER BY e.event_date DESC, e.id DESC) AS rank
            FROM season_results r JOIN season_events e ON e.id=r.event_id
            WHERE e.season_year=?
        ) WHERE rank=1""", (season_year,))


def assign_event_season(db_path, event_id, season_year):
    """Explicit operator correction; never infer a legacy season from its date."""
    validate_season(season_year, required=True)
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT season_year FROM season_events WHERE id=?", (event_id,)).fetchone()
        if existing is None:
            raise ValueError("Historical event no longer exists.")
        conn.execute("UPDATE season_events SET season_year=? WHERE id=?", (season_year, event_id))
        for year in {existing["season_year"], season_year} - {None}:
            _refresh_categories(conn, year)


def available_seasons(db_path):
    with get_conn(db_path) as conn:
        return [row[0] for row in conn.execute(
            "SELECT DISTINCT season_year FROM season_events WHERE season_year IS NOT NULL ORDER BY season_year DESC")]


def historical_performances(db_path, athlete_id, discipline, distance, season_year):
    """Distance-matched candidates for the seed engine, limited to two seasons.

    Return original times/statuses and source details; validity and fastest-time
    selection belong to the Stage 3 seed service. Unknown distances never match.
    """
    validate_season(season_year, required=True)
    if discipline not in {"run", "swim"}:
        raise ValueError("Discipline must be run or swim.")
    if type(distance) is not int or distance <= 0:
        raise ValueError("Distance must be positive whole metres.")
    with get_conn(db_path) as conn:
        return [dict(row) for row in conn.execute(f"""
            SELECT r.athlete_id, r.category, r.{discipline}_time AS time,
                r.{discipline}_distance AS distance, r.status,
                e.id AS event_id, e.name AS event_name, e.event_date, e.season_year
            FROM season_results r JOIN season_events e ON e.id=r.event_id
            WHERE r.athlete_id=? AND r.{discipline}_distance=? AND e.season_year IN (?, ?)
            ORDER BY e.season_year DESC, e.event_date DESC, e.id DESC
        """, (athlete_id, distance, season_year, season_year - 1))]


def set_affiliation(db_path, athlete_id: int, affiliated: bool) -> None:
    """Explicit manual corrections may set either value; imports only promote."""
    if not isinstance(affiliated, bool):
        raise ValueError("Affiliation must be Yes or No.")
    with get_conn(db_path) as conn:
        cursor = conn.execute("UPDATE season_athletes SET affiliated=? WHERE id=?", (int(affiliated), athlete_id))
        if cursor.rowcount != 1:
            raise ValueError("Athlete no longer exists.")


def season_snapshot(db_path, season_year="all") -> dict[str, list[dict]]:
    """Read one consistent snapshot; None selects unassigned legacy records.

    The default all-season view preserves existing callers and backup exports.
    Interactive reports pass an explicit season so attendance and awards are scoped.
    """
    if season_year != "all":
        validate_season(season_year)
    scope = "" if season_year == "all" else "WHERE e.season_year IS ?"
    params = () if season_year == "all" else (season_year,)
    with get_conn(db_path) as conn:
        conn.execute("BEGIN")
        events = conn.execute(f"""
            SELECT e.*, COUNT(r.athlete_id) AS result_count FROM season_events e
            LEFT JOIN season_results r ON r.event_id=e.id {scope} GROUP BY e.id ORDER BY e.event_date, e.id
        """, params).fetchall()
        athlete_scope = scope + " AND e.id IS NOT NULL" if scope else ""
        athletes = conn.execute(f"""
            SELECT a.*, COUNT(r.event_id) AS events_attended FROM season_athletes a
            LEFT JOIN season_results r ON r.athlete_id=a.id
            LEFT JOIN season_events e ON e.id=r.event_id
            {athlete_scope} GROUP BY a.id ORDER BY a.athlete_name, a.athlete_number
        """, params).fetchall()
        results = conn.execute(f"""
            SELECT r.*, a.athlete_number, e.name AS event_name, e.event_date, e.competition_type, e.season_year
            FROM season_results r JOIN season_athletes a ON a.id=r.athlete_id
            JOIN season_events e ON e.id=r.event_id {scope} ORDER BY e.event_date, e.id, r.category, CAST(r.position AS INTEGER), a.id
        """, params).fetchall()
        awards = conn.execute(f"""
            SELECT w.*, a.athlete_number, a.athlete_name, e.name AS event_name, e.event_date
            FROM season_awards w JOIN season_athletes a ON a.id=w.athlete_id
            JOIN season_events e ON e.id=w.event_id {scope} ORDER BY e.event_date, e.id, w.award_type, w.placing
        """, params).fetchall()
        records = conn.execute("SELECT * FROM season_record_benchmarks ORDER BY category_key").fetchall()
        templates = conn.execute("SELECT source_filename, content FROM season_record_templates").fetchall()
        categories = conn.execute("SELECT * FROM athlete_seasons WHERE season_year IS ?", (season_year,)).fetchall()
    snapshot = {key: [dict(row) for row in rows] for key, rows in
            (("events", events), ("athletes", athletes), ("results", results), ("awards", awards), ("records", records), ("record_templates", templates))}
    if season_year == "all":
        # The retained profile category column is legacy compatibility data only.
        # Derive displayed categories from competed results, not import order.
        latest = {}
        for result in sorted(snapshot["results"], key=lambda r: (r["season_year"] or 0, r["event_date"], r["event_id"])):
            latest[result["athlete_id"]] = result["category"]
        snapshot["athletes"] = [dict(a, category=latest.get(a["id"], a["category"])) for a in snapshot["athletes"]]
        return snapshot
    by_athlete = {}
    for row in snapshot["results"]:
        by_athlete.setdefault(row["athlete_id"], []).append(row)
    category_by_athlete = {r["athlete_id"]: r["category"] for r in categories if r["season_year"] == season_year}
    snapshot["athletes"] = [dict(a, events_attended=len(by_athlete[a["id"]]),
        category=category_by_athlete.get(a["id"], by_athlete[a["id"]][-1]["category"]))
        for a in snapshot["athletes"] if a["id"] in by_athlete]
    return snapshot
