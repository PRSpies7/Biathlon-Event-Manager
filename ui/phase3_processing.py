from __future__ import annotations

import pandas as pd
import streamlit as st

from database.repository import get_athletes
from parsers.run_results_excel import parse_run_results_excel
from parsers.swim_results import parse_swim_results
from services.results_service import process_run_results, process_swim_results


def _show_result(kind: str, result: dict):
    count = int(result.get("matched_count", 0))
    warnings = result.get("warnings", [])
    issues = result.get("issues", [])

    source_count = (
        int(result.get("source_timed_count", count))
        if kind == "Run"
        else int(result.get("source_result_count", count))
    )
    uncommitted = int(
        result.get("uncommitted_count", max(0, source_count - count))
    )

    if result.get("saved"):
        if kind == "Run":
            st.markdown(
                f'<div class="processing-summary"><strong>Run:</strong> '
                f'{count} of {source_count} valid results saved to the Master Dataset.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="processing-summary"><strong>{kind}:</strong> '
                f'{count} of {source_count} valid results saved to the Master Dataset.</div>',
                unsafe_allow_html=True,
            )
    elif kind == "Run" and source_count:
        st.warning(
            f"⚠ {source_count} timed result(s) were found in the source file, "
            "but none were saved to the Master Dataset."
        )
    elif issues:
        st.error(f"{kind} results were not saved because no valid records could be committed.")
    else:
        st.markdown(
            f'<div class="processing-summary"><strong>{kind}:</strong> '
            f'no valid results were found to save.</div>',
            unsafe_allow_html=True,
        )

    details = []
    details.extend(warnings)
    details.extend(issues)

    # Keep reconciliation and diagnostic information inside the expandable
    # processing-details area so it never pushes the working tables downward.
    show_reconciliation = source_count is not None
    if details or show_reconciliation:
        st.markdown('<div class="processing-card">', unsafe_allow_html=True)
        with st.expander(f"{kind} processing details", expanded=False):
            if show_reconciliation:
                noun = "timed result(s)" if kind == "Run" else "result(s)"
                st.markdown(
                    f'<div class="processing-reconciliation">'
                    f'<strong>{kind} reconciliation</strong><br>'
                    f'{source_count} {noun} found in the source file.<br>'
                    f'{count} valid result(s) saved to the Master Dataset.'
                    + (
                        f'<br>{uncommitted} result(s) were not committed and require attention.'
                        if uncommitted else
                        '<br>All source results were successfully committed.'
                    )
                    + '</div>',
                    unsafe_allow_html=True,
                )
            for detail in details[:100]:
                st.write(f"• {detail}")
        st.markdown('</div>', unsafe_allow_html=True)


def render(db_path: str, event_id: int):
    st.header("Phase 3 · Results Ingestion")
    st.caption("Process the run and swim files independently. Valid results are committed to the persistent SQLite Master Dataset.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Run Results")
        run_file = st.file_uploader("Upload Run Results Excel", type=["xlsx"], key=f"run_results_{event_id}")
        if run_file:
            try:
                parsed = parse_run_results_excel(run_file)
                st.session_state[f"run_parse_{event_id}"] = parsed
                st.toast(f"Run file loaded: {len(parsed['blocks'])} heat section(s) detected.", icon="✅")
                if parsed.get("imported_heat_numbers"):
                    st.caption(
                        f"Detected heats ({len(parsed['imported_heat_numbers'])}): "
                        + ", ".join(map(str, parsed["imported_heat_numbers"]))
                    )
            except Exception as exc:
                st.error(f"Run file could not be parsed: {exc}")
                st.session_state.pop(f"run_parse_{event_id}", None)

        run_data = st.session_state.get(f"run_parse_{event_id}")
        if run_data:
            if st.button("Process Run Results", type="primary", key=f"process_run_{event_id}"):
                result = process_run_results(db_path, event_id, run_data)
                st.session_state[f"last_run_process_{event_id}"] = result
                st.rerun()
            last_run = st.session_state.get(f"last_run_process_{event_id}")
            if last_run:
                _show_result("Run", last_run)
            if run_data and run_data.get("revisions"):
                with st.expander(f"Run file notes ({len(run_data['revisions'])})", expanded=False):
                    st.write(f"{len(run_data['revisions'])} repeated/revised run section(s) detected. The later section is used.")

    with col2:
        st.subheader("Swim Results")
        swim_file = st.file_uploader("Upload Swim Results TXT", type=["txt"], key=f"swim_results_{event_id}")
        if swim_file:
            try:
                parsed = parse_swim_results(swim_file)
                st.session_state[f"swim_parse_{event_id}"] = parsed
                st.toast(f"Swim file loaded: {len(parsed['sections'])} result section(s) detected.", icon="✅")
                detected_swim_heats = sorted({int(section["heat"]) for section in parsed.get("sections", [])})
                if detected_swim_heats:
                    st.caption(
                        f"Detected heats ({len(detected_swim_heats)}): "
                        + ", ".join(map(str, detected_swim_heats))
                    )
            except Exception as exc:
                st.error(f"Swim file could not be parsed: {exc}")
                st.session_state.pop(f"swim_parse_{event_id}", None)

        swim_data = st.session_state.get(f"swim_parse_{event_id}")
        if swim_data:
            if st.button("Process Swim Results", type="primary", key=f"process_swim_{event_id}"):
                result = process_swim_results(db_path, event_id, swim_data)
                st.session_state[f"last_swim_process_{event_id}"] = result
                st.rerun()
            last_swim = st.session_state.get(f"last_swim_process_{event_id}")
            if last_swim:
                _show_result("Swim", last_swim)

    st.divider()
    st.subheader("Current Master Dataset Results")
    athletes = get_athletes(db_path, event_id)
    if athletes:
        search_value = st.text_input(
            "Search athlete",
            placeholder="Athlete number or name...",
            key=f"phase3_search_{event_id}",
        )
        search = search_value.strip().lower()
        clear_col, count_col = st.columns([1.5, 5.5])
        with clear_col:
            if st.button("Clear Search", key=f"clear_phase3_search_{event_id}", disabled=not search):
                st.session_state[f"phase3_search_{event_id}"] = ""
                st.rerun()
        with count_col:
            st.caption("Clear Search restores the full Master Dataset.")
        filtered_athletes = [
            a for a in athletes
            if not search
            or search in str(a.get("athlete_number", "")).lower()
            or search in str(a.get("athlete_name", "")).lower()
        ]
        df = pd.DataFrame([
            {
                "Athlete No.": a["athlete_number"],
                "Age Group": a.get("group_name") or "",
                "Athlete Name": a["athlete_name"],
                "Run Heat": a.get("running_heat") or "",
                "Run Position": a.get("run_position") if a.get("run_position") is not None else "",
                "Runtime": a.get("run_time") or "",
                "Swim Heat": a.get("swimming_heat") or "",
                "Swim Lane": a.get("swimming_lane") or "",
                "Swimtime": a.get("swim_time") or "",
                "Status": "✓ Complete" if a.get("run_time") and a.get("swim_time") else "Incomplete",
            }
            for a in filtered_athletes
        ])
        st.caption(f"{len(filtered_athletes)} of {len(athletes)} athlete(s) shown.")
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("The Master Dataset is currently empty.")
