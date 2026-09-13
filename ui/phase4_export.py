from __future__ import annotations
from pathlib import Path

import pandas as pd
import streamlit as st

from database.repository import clear_results, get_athletes, get_event, update_manual_time
from exporters.filenames import event_results_filename
from exporters.master_excel import build_master_import_xlsx
from exporters.results_xml import build_results_xml
from validation.validators import normalize_time, validate_times


def _dataset_for_editor(athletes):
    return pd.DataFrame([
        {
            "Athlete No.": a["athlete_number"],
            "Athlete Name": a["athlete_name"],
            "Age Group": a.get("group_name") or "",
            "Run Heat": a.get("running_heat") or "",
            "Swim Heat": a.get("swimming_heat") or "",
            "Runtime": a.get("run_time") or "",
            "Swimtime": a.get("swim_time") or "",
        }
        for a in athletes
    ])


def _normalize_editor_times(edited: pd.DataFrame, current_by_id: dict[str, dict]) -> tuple[pd.DataFrame, list[str], dict[str, dict[str, str | None]]]:
    errors: list[str] = []
    normalized_rows: list[dict] = []
    changes: dict[str, dict[str, str | None]] = {}
    for _, row in edited.iterrows():
        aid = str(row["Athlete No."]).strip()
        current = current_by_id.get(aid)
        if not current:
            continue
        out = row.to_dict()
        changes[aid] = {}
        for label, field in (("Runtime", "run_time"), ("Swimtime", "swim_time")):
            raw = row[label]
            raw_text = "" if pd.isna(raw) else str(raw).strip()
            normalized = normalize_time(raw_text) if raw_text else None
            if raw_text and normalized is None:
                errors.append(f"Athlete {aid}: invalid {label} '{raw_text}'. Expected a time such as 04:12.50.")
            out[label] = normalized or ""
            original = current.get(field) or ""
            if normalized != original:
                changes[aid][field] = normalized
        normalized_rows.append(out)
    return pd.DataFrame(normalized_rows), errors, changes


def render(db_path: str, event_id: int):
    st.header("Phase 4 · Final Results & Export")
    athletes = get_athletes(db_path, event_id)
    if not athletes:
        st.warning("No event data is available.")
        return

    complete = [a for a in athletes if a.get("run_time") and a.get("swim_time")]
    excluded = [a for a in athletes if not (a.get("run_time") and a.get("swim_time"))]

    c1, c2, c3 = st.columns(3)
    c1.metric("Master athletes", len(athletes))
    c2.metric("Complete final results", len(complete))
    c3.metric("Incomplete", len(excluded))

    st.subheader("Final Results")
    st.caption("Runtime and Swimtime can be edited. Changes are saved only when you click Save Changes and override imported values.")

    search_value = st.text_input(
        "Search athlete",
        placeholder="Athlete number or name...",
        key=f"phase4_search_{event_id}",
    )
    search = search_value.strip().lower()
    clear_col, count_col = st.columns([1.5, 5.5])
    with clear_col:
        if st.button("Clear Search", key=f"clear_phase4_search_{event_id}", disabled=not search):
            st.session_state[f"phase4_search_{event_id}"] = ""
            st.rerun()
    with count_col:
        st.caption("Clear Search restores the full Final Results list.")
    filtered_athletes = [
        a for a in athletes
        if not search
        or search in str(a.get("athlete_number", "")).lower()
        or search in str(a.get("athlete_name", "")).lower()
    ]
    st.caption(f"{len(filtered_athletes)} of {len(athletes)} athlete(s) shown.")

    editor_df = _dataset_for_editor(filtered_athletes)
    edited = st.data_editor(
        editor_df,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"phase4_editor_{event_id}_{search or "all"}",
        column_config={
            "Athlete No.": st.column_config.TextColumn("Athlete No.", disabled=True, width="small"),
            "Athlete Name": st.column_config.TextColumn("Athlete Name", disabled=True, width="medium"),
            "Age Group": st.column_config.TextColumn("Age Group", disabled=True, width="small"),
            "Run Heat": st.column_config.TextColumn("Run Heat", disabled=True, width="small"),
            "Swim Heat": st.column_config.TextColumn("Swim Heat", disabled=True, width="small"),
            "Runtime": st.column_config.TextColumn("Runtime", width="small", help="Accepts common punctuation variants and normalizes to MM:SS.ss."),
            "Swimtime": st.column_config.TextColumn("Swimtime", width="small", help="Accepts common punctuation variants and normalizes to MM:SS.ss."),
        },
    )

    if st.button("Save Changes", type="primary", key=f"save_phase4_{event_id}"):
        normalized_df, errors, changes = _normalize_editor_times(edited, {str(a["athlete_number"]): a for a in athletes})
        if errors:
            for error in errors:
                st.error(error)
        else:
            changed_count = 0
            for aid, fields in changes.items():
                for field, value in fields.items():
                    update_manual_time(db_path, event_id, aid, field, value)
                    changed_count += 1
            st.session_state.pop(f"phase4_editor_{event_id}", None)
            if changed_count:
                st.success(f"{changed_count} manual time change(s) saved to the Master Dataset.")
                st.rerun()
            else:
                st.info("No changes were detected.")

    # Always reload from SQLite after any save so exports use the authoritative dataset.
    athletes = get_athletes(db_path, event_id)
    complete = [a for a in athletes if a.get("run_time") and a.get("swim_time")]
    excluded = [a for a in athletes if not (a.get("run_time") and a.get("swim_time"))]
    invalid_complete = validate_times(complete, require_complete=True)

    if excluded:
        st.warning(f"{len(excluded)} athlete(s) are incomplete and will not be included in the final XLSX/XML export until both times are present.")

    if invalid_complete:
        st.error("Final validation failed. Correct the highlighted time values before exporting.")
        for issue in invalid_complete[:50]:
            st.write(f"• {issue}")
        return

    st.divider()
    st.subheader("Final Output")
    if complete:
        st.success("Final dataset is valid for export.")
    else:
        st.info("No complete results are currently available for export.")

    xlsx = build_master_import_xlsx(athletes)
    xml = build_results_xml(athletes)
    event = get_event(db_path, event_id)
    event_name = event["name"] if event else "Event"
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download Master Excel", data=xlsx, file_name=event_results_filename(event_name, "xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", disabled=not complete
        )
    with col2:
        st.download_button(
            "Download Results XML", data=xml, file_name=event_results_filename(event_name, "xml"),
            mime="application/xml", type="primary", disabled=not complete
        )

    st.divider()
    st.subheader("Historical results")
    st.caption(f"Season: {event['season_year']}. Save captured times for future seeding and Reports. Published points are preserved when official results already exist.")
    if st.button("Save / update captured times in history",key=f"save_history_{event_id}",disabled=not any(a.get("run_time") or a.get("swim_time") for a in athletes)):
        from database.season_db import season_database_path,init_season_db
        from services.workflow_history import save_workflow_results
        history_path=season_database_path(Path(__file__).resolve().parents[1])
        try:
            init_season_db(history_path)
            saved_id=save_workflow_results(db_path,history_path,event_id)
        except (ValueError,OSError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Captured times saved to Season {event['season_year']} (historical event {saved_id}).")
    with st.container(key="phase4_reset_container"):
        reset_col, _reset_spacer = st.columns([2.2, 7.8])
        with reset_col:
            if st.button("⚠ Reset Phase 4 Results", type="secondary", key=f"reset_phase4_{event_id}", use_container_width=True):
                st.session_state[f"confirm_reset_phase4_{event_id}"] = True
    st.markdown(
        '<div class="phase4-reset-description">'
        'This clears all imported and manually entered runtime/swimtime values. '
        'Athlete data, heats, lanes and Phase 2 run positions are preserved.'
        '</div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get(f"confirm_reset_phase4_{event_id}"):
        st.error("Are you sure? This cannot be undone from the current dataset. You can then perform a fresh Phase 3 import.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Cancel", key=f"cancel_reset_{event_id}"):
                st.session_state.pop(f"confirm_reset_phase4_{event_id}", None)
                st.rerun()
        with c2:
            if st.button("Confirm Reset Phase 4", type="primary", key=f"confirm_reset_btn_{event_id}"):
                clear_results(db_path, event_id)
                for key in (
                    f"confirm_reset_phase4_{event_id}", f"run_parse_{event_id}", f"swim_parse_{event_id}",
                    f"last_run_process_{event_id}", f"last_swim_process_{event_id}", f"phase4_editor_{event_id}"
                ):
                    st.session_state.pop(key, None)
                st.success("Phase 4 results have been reset. The Master Dataset and Phase 2 positions were preserved.")
                st.rerun()
