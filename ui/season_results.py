from __future__ import annotations

from dataclasses import replace
from datetime import date
from hashlib import sha256
from io import BytesIO
import sqlite3

import streamlit as st

from database.season_db import init_season_db, season_database_path
from database.season_repository import (EventAlreadyExists, reset_season_database,
    season_snapshot, set_affiliation, available_seasons, assign_event_season)
from parsers.season_results import parse_season_results
from parsers.season_results.models import COMPETITION_TYPES
from services.season_results_service import athlete_rows, import_event, import_summary
from ui.season_reports import render as render_reports

VIEWS = ("Import Results", "Imported Events", "Athlete Database", "Reports")


def _set_view(view):
    st.session_state.season_view = view


def _continue_navigation(view):
    index = VIEWS.index(view)
    st.divider()
    with st.container(key="season_navigation"):
        back, _, forward = st.columns([2.5, 1, 2.5], vertical_alignment="center")
        with back:
            if index > 0:
                st.button(f"← Back to {VIEWS[index - 1]}", key="season_back",
                          type="secondary", width="stretch", on_click=_set_view, args=(VIEWS[index - 1],))
        with forward:
            if index < len(VIEWS) - 1:
                st.button(f"Continue to {VIEWS[index + 1]} →", key="season_continue",
                          type="primary", width="stretch", on_click=_set_view, args=(VIEWS[index + 1],))


def _imports(db_path):
    st.subheader("Upload published final results for the current season")
    st.caption("Multiple files are accepted.")
    uploads = st.file_uploader("Final results files", type=["pdf", "xlsx"], accept_multiple_files=True,
                              key=f"season_uploads_{st.session_state.get('season_upload_generation', 0)}")
    if st.button("Preview results", disabled=not uploads, key="season_preview"):
        pending = []
        errors = []
        with st.spinner("Reading result files…"):
            for i, upload in enumerate(uploads):
                payload = upload.getvalue()
                token = sha256(payload + upload.name.encode()).hexdigest()[:16] + f"_{i}"
                try:
                    parsed = parse_season_results(BytesIO(payload), upload.name)
                    pending.append({"event": parsed, "token": token, "outcome": ""})
                except Exception as exc:
                    errors.append(f"{upload.name}: {exc}")
        # Session state holds only the temporary preview; saved data lives in SQLite.
        st.session_state.season_pending = pending
        st.session_state.season_parse_errors = errors
    for error in st.session_state.get("season_parse_errors", []):
        st.error(error)
    pending = st.session_state.get("season_pending", [])
    if not pending:
        return
    st.subheader("Pre-import summary")
    summaries, decisions, seen = [], [], set()
    ready = True
    for item in pending:
        event, token = item["event"], item["token"]
        if item["outcome"]:
            st.success(f"{event.source_filename}: {item['outcome']}")
            continue
        with st.container(border=True):
            st.write(event.source_filename)
            for note in event.notes:
                st.info(note)
            with st.expander("Event details", expanded=bool(event.notes)):
                name = st.text_input("Event name", event.name, key=f"season_name_{token}")
                event_date = st.date_input("Event date", value=event.event_date, key=f"season_date_{token}")
                season_year = st.number_input("Season", min_value=1900, max_value=9999,
                    value=event.season_year or date.today().year, step=1, key=f"season_year_{token}",
                    help="Confirm the competition season. It can differ from the event's calendar year.")
                competition_type = st.selectbox("Competition type", COMPETITION_TYPES,
                    index=COMPETITION_TYPES.index(event.competition_type) if event.competition_type else None,
                    placeholder="Confirm competition type", key=f"season_type_{token}")
            candidate = replace(event, name=name, event_date=event_date, competition_type=competition_type or "",
                                season_year=int(season_year))
            summary = import_summary(db_path, candidate)
            from services.season_scope import gn_event
            candidate = gn_event(candidate)
            identity = (candidate.identity, event_date, competition_type, candidate.season_year)
            duplicate = summary["Status"] == "Already Imported" or identity in seen
            if identity in seen:
                summary["Status"] = "Already Imported (earlier in this batch)"
            if duplicate:
                st.warning("This event already exists. Overwrite the existing event results or skip this event?")
                action = st.radio("Action", ("Overwrite", "Skip"), index=1, horizontal=True, key=f"season_action_{token}")
            else:
                action = "Import" if st.checkbox("Import this event", value=True, key=f"season_include_{token}") else "Skip"
            if action != "Skip":
                try:
                    candidate.check_structure()
                except ValueError as exc:
                    st.info(str(exc))
                    ready = False
                seen.add(identity)
            summaries.append(summary)
            decisions.append((item, candidate, action))
    if summaries:
        st.dataframe(summaries, hide_index=True, width="stretch")
        if st.button("Import selected results", type="primary", disabled=not ready, key="season_import"):
            for item, event, action in decisions:
                try:
                    event_id = import_event(db_path, event, action)
                    item["outcome"] = "Skipped" if event_id is None else f"{'Replaced' if action == 'Overwrite' else 'Imported'} {event.name} ({len(event.results)} results)"
                except EventAlreadyExists:
                    st.warning("An event was imported after this preview. Review its Overwrite / Skip choice.")
                    return
                except Exception:
                    st.error(f"Could not save {event.source_filename}. Its transaction was rolled back; any other completed imports remain saved. Check the database configuration and retry.")
                    return
            st.rerun()


def _events(snapshot):
    st.subheader("Current database for the current season")
    if not snapshot["events"]:
        st.info("No events imported yet.")
        return
    st.dataframe([{
        "Event ID": e["id"], "Event name": e["name"], "Date": e["event_date"],
        "Season": e["season_year"] if e["season_year"] is not None else "Unassigned",
        "Competition type": e["competition_type"], "Results": e["result_count"],
        "Source file": e["source_filename"], "Imported at (UTC)": e["imported_at"],
    } for e in snapshot["events"]], hide_index=True, width="stretch")


def _athletes(db_path, snapshot):
    if not snapshot["athletes"]:
        st.info("Import an event to start the season athlete list.")
        return
    search = st.text_input("Search athlete number, name, school or team", key="season_search").casefold().strip()
    affiliation = st.selectbox("Affiliation filter", ["All", "Affiliated", "Not Affiliated"], key="season_filter")
    rows = [r for r in athlete_rows(snapshot) if
            (not search or search in " ".join(str(v) for v in r.values()).casefold())
            and (affiliation == "All" or r["Affiliated"] == affiliation)]
    st.dataframe(rows, hide_index=True, width="stretch")
    numbers = {r["Athlete number"] for r in rows}
    choices = {a["id"]: a for a in snapshot["athletes"] if a["athlete_number"] in numbers}
    if not choices:
        return
    selected = st.selectbox("Inspect athlete / correct affiliation", list(choices),
        format_func=lambda key: f"{choices[key]['athlete_number']} · {choices[key]['athlete_name']}", key="season_athlete")
    athlete = choices[selected]
    with st.form(f"season_affiliation_form_{selected}"):
        affiliated = st.checkbox("Affiliated", value=bool(athlete["affiliated"]))
        if st.form_submit_button("Save affiliation"):
            set_affiliation(db_path, selected, affiliated)
            st.rerun()
    st.caption("Manual corrections can set Yes or No. Later imports can promote an athlete to affiliated, but never remove affiliation.")
    st.dataframe([{k.replace("_", " ").capitalize(): v for k, v in r.items() if k not in {"event_id", "athlete_id"}}
                  for r in snapshot["results"] if r["athlete_id"] == selected], hide_index=True)


def _confirm_database_reset(db_path, season_year=None):
    reset_season_database(db_path, season_year)
    generation = st.session_state.get("season_upload_generation", 0) + 1
    for key in list(st.session_state):
        if key.startswith("season_") and key != "season_view":
            st.session_state.pop(key, None)
    st.session_state.season_upload_generation = generation
    st.session_state.season_reset_notice = True


def _reset_database_controls(db_path, snapshot, season_year=None):
    st.divider()
    with st.container(key="season_reset_container"):
        reset_col, _ = st.columns([2.2, 7.8])
        with reset_col:
            if st.button("⚠ Reset Database", key="season_reset", type="secondary", width="stretch",
                         disabled=not (snapshot["events"] or snapshot["athletes"] or snapshot.get("records"))):
                st.session_state.season_confirm_reset = True
    st.caption("Reset removes the selected season's events, results and awards. Shared athletes and record references are retained for assigned seasons.")
    if st.session_state.get("season_confirm_reset"):
        st.error("This permanently deletes the selected season's imported results. This cannot be undone. Event Management sessions are unaffected.")
        cancel, confirm = st.columns(2)
        with cancel:
            if st.button("Cancel", key="season_cancel_reset"):
                st.session_state.pop("season_confirm_reset", None)
                st.rerun()
        with confirm:
            st.button("Confirm Reset Database", key="season_confirm_reset_button", type="primary",
                      on_click=_confirm_database_reset, args=(db_path, season_year))


def render(base_dir):
    st.header("Season Results Database")
    st.caption("One historical database holds all seasons. Season is selected explicitly, independently of event date.")
    if st.session_state.pop("season_reset_notice", False):
        st.success("The season database has been reset. You can import results for a new season.")
    try:
        db_path = season_database_path(base_dir)
        init_season_db(db_path)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    except sqlite3.Error:
        st.error("The season database could not be opened. Check that its configured folder is writable and the file is a SQLite database.")
        return
    view = st.session_state.get("season_view", VIEWS[0])
    if view == "Import Results":
        _imports(db_path)
        _continue_navigation(view)
        return
    years = available_seasons(db_path)
    selected_year = st.selectbox("Season", [*years, None],
        format_func=lambda year: str(year) if year is not None else "Unassigned (legacy)",
        key="season_selected_year", on_change=lambda: st.session_state.pop("season_confirm_reset", None))
    snapshot = season_snapshot(db_path, selected_year)
    if selected_year is None and snapshot["events"]:
        st.warning("These records have no confirmed season and are excluded from historical seed lookup. Assign a season in Imported Events.")
    if view == "Imported Events":
        _events(snapshot)
        if selected_year is None and snapshot["events"]:
            with st.expander("Assign a season to a legacy event"):
                choices = {e["id"]: e for e in snapshot["events"]}
                event_id = st.selectbox("Event", list(choices),
                    format_func=lambda key: f"{choices[key]['name']} · {choices[key]['event_date']}")
                year = st.number_input("Confirmed season", min_value=1900, max_value=9999, value=date.today().year)
                if st.button("Assign season"):
                    try:
                        assign_event_season(db_path, event_id, int(year))
                    except (ValueError, sqlite3.IntegrityError) as exc:
                        st.error(f"Could not assign season: {exc}")
                    else:
                        st.rerun()
    elif view == "Athlete Database":
        _athletes(db_path, snapshot)
        if selected_year is not None or not years:
            _reset_database_controls(db_path, snapshot, selected_year)
    elif view == "Reports":
        render_reports(db_path, snapshot)
    _continue_navigation(view)
