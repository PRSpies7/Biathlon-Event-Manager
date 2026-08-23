from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from database.repository import create_event, replace_athletes, get_event, get_athletes
from exporters.swim_timekeeper import build_swim_timekeeper_xlsx
from exporters.timedrops_json import generate_timedrops_json, dumps_json
from parsers.master_entries import parse_master_entries
from parsers.master_entries_pdf import infer_pdf_event_defaults
from validation.validators import validate_master


def _generated_dir(db_path: str) -> Path:
    return Path(db_path).resolve().parent / "generated"


def _json_path(db_path: str, event_id: int) -> Path:
    return _generated_dir(db_path) / f"event_{event_id}_meet_program.json"


def _render_persistent_event(db_path: str, event_id: int):
    event = get_event(db_path, event_id)
    athletes = get_athletes(db_path, event_id)
    if not event or not athletes:
        return False

    st.success("Event is already initialized. The persistent Master Dataset and Phase 1 exports are available.")
    st.subheader("Current Event")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div class="event-info-card"><div class="event-info-label">Event Name</div><div class="event-info-value">{event["name"]}</div></div>', unsafe_allow_html=True)
    with col2:
        course_label = "Long Course" if event["course"] == "LCM" else "Short Course"
        st.markdown(f'<div class="event-info-card event-info-course"><div class="event-info-label">Pool Course</div><div class="event-info-value">{course_label}</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="event-info-card event-info-course"><div class="event-info-label">Pool Lanes</div><div class="event-info-value">{event["pool_lanes"]}</div></div>', unsafe_allow_html=True)

    st.caption(f'{len(athletes)} athletes are stored in the persistent Master Dataset.')
    st.subheader("Phase 1 Exports")

    json_path = _json_path(db_path, event_id)
    if json_path.exists():
        json_data = json_path.read_text(encoding="utf-8")
    else:
        json_data = ""
        st.warning("The stored meet_program.json file is not available for this event. Re-upload the Master Entries workbook if it needs to be regenerated.")

    swim_xlsx = build_swim_timekeeper_xlsx(
        athletes,
        event["name"],
        int(event["pool_lanes"]),
    )
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download meet_program.json",
            data=json_data,
            file_name="meet_program.json",
            mime="application/json",
            type="primary",
            disabled=not bool(json_data),
            key=f"download_meet_program_{event_id}",
        )
    with col2:
        st.download_button(
            "Download Swim Timekeeper Sheets",
            data=swim_xlsx,
            type="primary",
            file_name=f'{event["name"].strip() or "Event"} Swim Lanes.xlsx',
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_swim_lanes_{event_id}",
        )
    return True


def render(db_path: str, reference_json: dict):
    st.header("Phase 1 · Event Setup")

    # Phase 1 completion is persistent event state. Returning to this phase
    # must not make the operator re-upload the Master Entries workbook.
    event_id = st.session_state.get("event_id")
    if event_id and _render_persistent_event(db_path, event_id):
        return

    upload_key = f"master_entries_{st.session_state.get('new_session_token', 0)}"
    uploaded = st.file_uploader(
        "Master Entries Excel or PDF",
        type=["xlsx", "pdf"],
        key=upload_key,
        help="Drop either the Master Entries Excel workbook or the Meet Program PDF. The application detects the format automatically.",
    )
    if not uploaded:
        st.info("Upload the Master Entries Excel or PDF file to begin. This will create the Master Dataset, meet_program.json, and Swim Lane Sheets.")
        return

    source_type = Path(uploaded.name).suffix.lower()
    try:
        parsed = parse_master_entries(uploaded)
    except Exception as exc:
        source_label = "PDF" if source_type == ".pdf" else "Excel workbook"
        st.error(f"Could not read the Master Entries {source_label}: {exc}")
        return

    # Excel and PDF inputs now converge into the same Phase 1 confirmation
    # workflow. The PDF supplies the athlete/heat/lane dataset and sensible
    # inferred defaults, but it must NOT auto-initialize the event. The
    # operator needs the same opportunity to review/edit event settings before
    # the SQLite event, meet_program.json and Swim Lane Sheets are created.
    athletes = parsed["athletes"]
    issues = validate_master(athletes)
    if issues:
        st.error("Master data validation failed.")
        for issue in issues:
            st.write(f"• {issue}")
        return

    is_pdf = source_type == ".pdf"
    pdf_defaults = infer_pdf_event_defaults(uploaded.name) if is_pdf else None
    inferred_lanes = max(
        [int(r["lane"]) for r in parsed["swimming_records"] if r["lane"] is not None] or [8]
    )

    if is_pdf:
        st.info(
            "PDF detected. The athlete, heat and lane data has been imported. "
            "Review or edit the Phase 1 event settings below before initializing the event."
        )

    col1, col2, col3 = st.columns(3)
    with col1:
        meet_name = st.text_input(
            "Meet name",
            value=(pdf_defaults["meet_name"] if pdf_defaults else Path(uploaded.name).stem),
        )
        host_team = st.text_input(
            "Host / Team name",
            value=(pdf_defaults["host_team"] if pdf_defaults else "Gauteng North Biathlon"),
        )
    with col2:
        default_start = date.fromisoformat(pdf_defaults["start_date"]) if pdf_defaults and pdf_defaults["start_date"] else date.today()
        start_date = st.date_input("Meet start date", value=default_start)
        course = st.selectbox(
            "Pool course",
            ["LCM", "SCM"],
            index=0 if (pdf_defaults or {}).get("course", "LCM") == "LCM" else 1,
        )
    with col3:
        pool_lanes = st.number_input("Pool lanes", min_value=1, max_value=12, value=inferred_lanes, step=1)
        timezone = st.text_input(
            "TimeDrops UTC offset",
            value=(pdf_defaults["timezone"] if pdf_defaults else "+02:00"),
        )

    st.subheader("Imported Master Dataset")
    preview = pd.DataFrame(athletes)[[
        "athlete_number", "athlete_name", "group_name", "running_heat", "running_lane", "swimming_heat", "swimming_lane"
    ]].rename(columns={
        "athlete_number": "Athlete Number", "athlete_name": "Athlete Name", "group_name": "Age Group",
        "running_heat": "Run Heat", "running_lane": "Run Lane", "swimming_heat": "Swim Heat", "swimming_lane": "Swim Lane"
    })
    st.dataframe(preview, use_container_width=True, hide_index=True)
    st.caption(f"{len(athletes)} unique athletes · {len(parsed['running_heats'])} running heats · {len(parsed['swimming_heats'])} swimming heats")

    if parsed["swimming_only_athletes"]:
        st.warning(f"{len(parsed['swimming_only_athletes'])} athlete(s) appear in swimming but not running entries.")

    if st.button("Confirm Data Set and Initialize Event", type="primary"):
        if not meet_name.strip() or not host_team.strip():
            st.error("Meet name and host/team name are required.")
            return
        try:
            event_id = create_event(db_path, meet_name.strip(), host_team.strip(), start_date.isoformat(), course, int(pool_lanes))
            replace_athletes(db_path, event_id, athletes)
            json_data = generate_timedrops_json(
                reference_json, athletes, meet_name=meet_name.strip(), host_team=host_team.strip(),
                start_date=start_date.isoformat(), course=course, pool_lanes=int(pool_lanes),
                timezone_offset=timezone.strip() or "+02:00",
            )
            st.session_state.event_id = event_id
            st.session_state.timedrops_json = dumps_json(json_data)
            generated_dir = _generated_dir(db_path)
            generated_dir.mkdir(parents=True, exist_ok=True)
            _json_path(db_path, event_id).write_text(st.session_state.timedrops_json, encoding="utf-8")
            st.session_state.active_phase = 1
            st.success("Event initialized successfully. The persistent Master Dataset has been created.")
            st.rerun()
        except Exception as exc:
            st.error(f"Initialization failed: {exc}")
            return

    if st.session_state.get("event_id"):
        st.divider()
        st.subheader("Phase 1 Exports")
        json_data = st.session_state.get("timedrops_json", "")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Download meet_program.json", data=json_data, file_name="meet_program.json",
                mime="application/json", type="primary"
            )
        with col2:
            swim_xlsx = build_swim_timekeeper_xlsx(athletes, meet_name.strip(), int(pool_lanes))
            safe_name = meet_name.strip() or "Event"
            st.download_button(
                "Download Swim Timekeeper Sheets", data=swim_xlsx, type="primary",
                file_name=f"{safe_name} Swim Lanes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
