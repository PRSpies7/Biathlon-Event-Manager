from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from database.repository import create_event, replace_athletes, get_event, get_athletes, approve_heats
from exporters.timedrops_json import TIMEDROPS_UTC_OFFSET, generate_timedrops_json, dumps_json
from parsers.master_entries import parse_master_entries
from parsers.master_entries_pdf import infer_pdf_event_defaults
from validation.validators import validate_master
from services.competition import infer_season


def _generated_dir(db_path: str) -> Path:
    return Path(db_path).resolve().parent / "generated"


def _json_path(db_path: str, event_id: int) -> Path:
    return _generated_dir(db_path) / f"event_{event_id}_meet_program.json"


def _render_persistent_event(db_path: str, event_id: int):
    event = get_event(db_path, event_id)
    athletes = get_athletes(db_path, event_id)
    if not event or not athletes:
        return False

    from ui.heat_review import render as render_heat_review
    if event["heat_source"] == "generated" or event["heat_status"] != "approved":
        render_heat_review(db_path, event_id)
        return True

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
    if event["season_year"] is None:
        st.warning("This legacy event has no confirmed Season. Its date has not been used to assign one automatically.")
    else:
        st.caption(f'Season: {event["season_year"]}')
    from ui.heat_review import render_event_settings
    render_event_settings(db_path,dict(event))
    render_operational_outputs(db_path,event_id)
    return True


def render_operational_outputs(db_path,event_id):
    import json
    from services.heat_outputs import current_outputs,generate_outputs
    st.subheader("Phase 1 Exports")
    event=dict(get_event(db_path,event_id))
    files=current_outputs(db_path,event_id)
    if not files:
        st.info("Operational files need generation for the approved assignments.")
    if st.button("Generate / regenerate operational files",type="primary",key=f"generate_outputs_{event_id}"):
        reference=json.loads((Path(__file__).resolve().parents[1]/"data"/"TimeDrops JSON example.json").read_text(encoding="utf-8"))
        try:
            generate_outputs(db_path,event_id,reference)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    labels={
        "Combined Heats.pdf":("Download Combined Heat PDF",f"download_heats_pdf_{event_id}"),
        "Master Entries Heats.xlsx":("Download Master Entries Heats",f"download_heats_xlsx_{event_id}"),
        "Athlete Run Swim Lane Sheet.xlsx":("Download Athlete Run/Swim Lane Sheet",f"download_athlete_list_{event_id}"),
        "Swim Timekeeper Sheets.xlsx":("Download Swim Timekeeper Sheets",f"download_swim_lanes_{event_id}"),
        "meet_program.json":("Download meet_program.json",f"download_meet_program_{event_id}"),
    }
    for filename,(mime,content) in files.items():
        label,key=labels[filename]
        st.download_button(label,data=content,file_name=filename,mime=mime,key=key)
    st.caption("Files belong to the approved heat revision. After changing assignments, regenerate and replace any copies already downloaded.")


def render(db_path: str, reference_json: dict):
    st.header("Phase 1 · Event Setup")

    # Phase 1 completion is persistent event state. Returning to this phase
    # must not make the operator re-upload the Master Entries workbook.
    event_id = st.session_state.get("event_id")
    if event_id and _render_persistent_event(db_path, event_id):
        return

    upload_key = f"master_entries_{st.session_state.get('new_session_token', 0)}"
    heat_source = st.radio("Start event", ["Generate heats from entries", "Use existing heats"],
        index=1, horizontal=True, key=f"heat_source_{st.session_state.get('new_session_token', 0)}")
    generated = heat_source == "Generate heats from entries"
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
    metadata=parsed.get("metadata",{})
    defaults=dict(pdf_defaults or {})
    defaults.update(metadata)
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
            value=defaults.get("meet_name",Path(uploaded.name).stem),
        )
        host_team = st.text_input(
            "Host / Team name",
            value=defaults.get("host_team","Gauteng North Biathlon"),
        )
    with col2:
        default_start = date.fromisoformat(defaults["start_date"]) if defaults.get("start_date") else date.today()
        start_date = st.date_input("Meet start date", value=default_start)
        season_year = st.number_input("Season", min_value=1900, max_value=9999,
            value=metadata.get("season_year",infer_season(start_date)), step=1, key=f"event_season_{start_date}",
            help="Inferred from the meet date: seasons run August-July. Override if needed.")
        course = st.selectbox(
            "Pool course",
            ["LCM", "SCM"],
            index=0 if defaults.get("course", "SCM") == "LCM" else 1,
        )
    with col3:
        pool_lanes = st.number_input("Pool lanes", min_value=1, max_value=12,
            value=metadata.get("pool_lanes",inferred_lanes), step=1)
        meet_types=["Local", "Interprovincial", "National"]
        meet_type = st.selectbox("Meet type", meet_types, index=meet_types.index(defaults.get("meet_type","Local")))

    st.subheader("Imported Master Dataset")
    preview_columns = ["athlete_number", "athlete_name", "group_name"]
    if any(athlete.get("province") for athlete in athletes):
        preview_columns.append("province")
    preview_columns.extend(["running_heat", "running_lane", "swimming_heat", "swimming_lane"])
    preview = pd.DataFrame(athletes)[preview_columns].rename(columns={
        "athlete_number": "Athlete Number", "athlete_name": "Athlete Name", "group_name": "Age Group",
        "province": "Province",
        "running_heat": "Run Heat", "running_lane": "Run Lane", "swimming_heat": "Swim Heat", "swimming_lane": "Swim Lane"
    })
    st.dataframe(preview, use_container_width=True, hide_index=True)
    st.caption(f"{len(athletes)} unique athletes · {len(parsed['running_heats'])} running heats · {len(parsed['swimming_heats'])} swimming heats")

    if parsed["swimming_only_athletes"]:
        st.warning(f"{len(parsed['swimming_only_athletes'])} athlete(s) appear in swimming but not running entries.")

    if generated:
        from ui.heat_review import render_entries
        render_entries(db_path, parsed, uploaded, meet_name, host_team, start_date,
                       course, int(pool_lanes), meet_type, int(season_year))
        return

    if st.button("Confirm Data Set and Initialize Event", type="primary"):
        if not meet_name.strip() or not host_team.strip():
            st.error("Meet name and host/team name are required.")
            return
        try:
            json_data = generate_timedrops_json(
                reference_json, athletes, meet_name=meet_name.strip(), host_team=host_team.strip(),
                start_date=start_date.isoformat(), course=course, pool_lanes=int(pool_lanes),
                timezone_offset=TIMEDROPS_UTC_OFFSET, meet_type=meet_type,
            )
            event_id = create_event(
                db_path, meet_name.strip(), host_team.strip(), start_date.isoformat(), course,
                int(pool_lanes), meet_type=meet_type, season_year=int(season_year),
                run_positions=[int(p.strip()) for p in metadata["run_positions"].split(",")] if metadata.get("run_positions") else None,
            )
            from services.heats import enrich_imported
            replace_athletes(db_path, event_id, enrich_imported(athletes))
            approve_heats(db_path,event_id,get_event(db_path,event_id)["heat_revision"])
            from services.heat_outputs import generate_outputs
            st.session_state.event_id = event_id
            generate_outputs(db_path,event_id,reference_json)
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
