"""Pre-event entry confirmation and run/swim heat review."""
from pathlib import Path
from hashlib import sha256

import pandas as pd
import json
import streamlit as st

from database.repository import create_event, get_event, get_athletes, replace_athletes, update_event
from database.season_db import init_season_db, season_database_path
from services.seeding import prepare_entries, display_seed, select_seed
from services.competition import distances, infer_season


def seed_source(row, discipline):
    return "NT" if row.get(discipline+"_seed") is None else row.get(discipline+"_seed_source") or "Manual override"


def render_event_settings(db_path,event,pending_edits=False):
    with st.expander("Correct event season or lane configuration"):
        with st.form(f"event_configuration_{event['id']}"):
            year=st.number_input("Season",min_value=1900,max_value=9999,value=event["season_year"] or infer_season(event["start_date"]))
            lanes=st.number_input("Pool lanes",min_value=1,max_value=12,value=int(event["pool_lanes"]))
            if st.form_submit_button("Save event configuration",disabled=pending_edits):
                try:
                    update_event(db_path,event["id"],season_year=int(year),pool_lanes=int(lanes))
                    if int(year)!=event["season_year"] and event["heat_source"]=="generated":
                        from database.repository import save_heat_assignments
                        history_path=season_database_path(Path(__file__).resolve().parents[1])
                        init_season_db(history_path)
                        rows=get_athletes(db_path,event["id"])
                        revision=get_event(db_path,event["id"])["heat_revision"]
                        for row in rows:
                            for discipline in ("run","swim"):
                                if not str(row.get(discipline+"_seed_source") or "").startswith("Manual"):
                                    row[discipline+"_seed"],row[discipline+"_seed_source"]=select_seed(
                                        history_path,row.get("history_athlete_id"),discipline,row.get(discipline+"_distance"),int(year))
                        save_heat_assignments(db_path,event["id"],rows,revision)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()


def render_entries(db_path, parsed, uploaded, name, host, start_date, course, lanes, meet_type, year):
    history_path = season_database_path(Path(__file__).resolve().parents[1])
    init_season_db(history_path)
    token = sha256(uploaded.getvalue()).hexdigest()[:12] + f"_{year}"
    removed_key = f"entry_removals_{token}"
    removed = st.session_state.get(removed_key,set())
    parsed = dict(parsed,athletes=[r for r in parsed["athletes"] if r["athlete_number"] not in removed])
    notices = []
    matches = {}
    try:
        entries, ambiguous = prepare_entries(parsed, history_path, year)
    except ValueError as exc:
        st.error(str(exc))
        return
    unresolved = False
    blockers = []
    if any(not issue.get("number_matched") for issue in ambiguous):
        st.subheader("Check historical identities")
        st.caption("Athletes are linked by athlete number. Name differences are highlighted for reference; the uploaded name is retained.")
    for issue in ambiguous:
        row = issue["entry"]
        if issue.get("number_matched"):
            notices.append(f"{row['athlete_number']}: entry name {row['athlete_name']} differs from historical name {issue['candidates'][0]['athlete_name']}. Linked by athlete number; no action required.")
            continue
        choices = {a["id"]: f"Link historical record: {a['athlete_number']} · {a['athlete_name']}" for a in issue["candidates"]}
        choices[0] = "New / visiting athlete - no historical link"
        selection = st.selectbox(f"Confirm identity: {row['athlete_number']} · {row['athlete_name']}",
            list(choices), format_func=choices.get, index=None, key=f"identity_{token}_{row['athlete_number']}")
        if selection is None:
            unresolved = True
            blockers.append(f"{row['athlete_number']} · {row['athlete_name']}: choose a historical identity or New / visiting athlete.")
        else:
            matches[row["athlete_number"]] = selection or None
            st.success(f"Selection accepted for {row['athlete_name']}: {'historical seeds will be checked' if selection else 'no historical link; seed is NT'}. Save with Confirm Entries and Initialize Event below.")
    if matches:
        try:
            entries, _ = prepare_entries(parsed, history_path, year, matches)
        except ValueError as exc:
            st.error(str(exc))
            return
    st.subheader("Entries and event distances")
    from ui.heat_review_tables import duplicate_name_notices,show_entry_notices
    notices.extend(duplicate_name_notices(entries))
    notice_area = st.container()
    cached = st.session_state.get(f"entry_values_{token}",{})
    metadata = pd.DataFrame([{"Athlete": r["athlete_number"], "Name": r["athlete_name"],
        "Age group": r["group_name"], "Gender": r["gender"],
        "Run distance": r["run_distance"], "Swim distance": r["swim_distance"],
        **cached.get(r["athlete_number"],{}),"Remove from event": False} for r in entries])
    edited = st.data_editor(metadata, hide_index=True, key=f"entry_metadata_{token}_{len(removed)}",
        disabled=["Athlete", "Name"], column_config={
            "Gender": st.column_config.SelectboxColumn(options=["F", "M"]),
            "Run distance": st.column_config.NumberColumn(min_value=1, step=1),
            "Swim distance": st.column_config.SelectboxColumn(options=[25,50,100])})
    selected = set(edited.loc[edited["Remove from event"],"Athlete"])
    if st.button("Remove selected entries",key=f"remove_entries_{token}",disabled=not selected,
                 help="Remove the ticked entries from this upload before initializing the event. Historical results are retained."):
        if len(selected)==len(entries):
            st.error("Keep at least one entry to initialize the event.")
        else:
            st.session_state[removed_key] = removed|selected
            st.session_state[f"entry_values_{token}"] = {r["Athlete"]:r for r in edited.to_dict("records") if r["Athlete"] not in selected}
            st.rerun()
    invalid = unresolved
    for entry, (_, row) in zip(entries, edited.iterrows()):
        entry["group_name"], entry["gender"] = str(row["Age group"] or ""), str(row["Gender"] or "")
        if entry["gender"] not in {"F", "M"} or not entry["group_name"].strip():
            invalid = True
            blockers.append(f"{entry['athlete_number']} · {entry['athlete_name']}: enter a category and select gender F or M.")
        expected = distances(entry["group_name"])
        for index, discipline in enumerate(("run", "swim")):
            value = row[f"{discipline.title()} distance"]
            distance = None if pd.isna(value) else int(value)
            if entry[f"{discipline}_entered"] and not distance:
                invalid = True
                blockers.append(f"{entry['athlete_number']} · {entry['athlete_name']}: enter the {discipline} distance in the table above.")
            if distance and expected[index] and distance != expected[index]:
                notices.append(f"{entry['athlete_name']}: {discipline} distance {distance} m differs from the category rule ({expected[index]} m). The confirmed event distance will be used.")
            if entry[f"{discipline}_distance"] != distance:
                entry[f"{discipline}_seed"], entry[f"{discipline}_seed_source"] = select_seed(
                    history_path, entry["history_athlete_id"], discipline, distance, year)
            entry[f"{discipline}_distance"] = distance
    with notice_area:
        show_entry_notices(notices)
    if not entries:
        invalid = True
        blockers.append("Keep at least one entry to initialize the event.")
    st.subheader("Entries and historical seeds")
    st.dataframe([{"Athlete":r["athlete_number"], "Name":r["athlete_name"],
        "Run seed":display_seed(r["run_seed"]), "Run source":seed_source(r,"run"),
        "Swim seed":display_seed(r["swim_seed"]), "Swim source":seed_source(r,"swim")} for r in entries], hide_index=True)
    confirmed = st.checkbox(f"Confirm pool capacity: {lanes} lanes", key=f"confirm_lanes_{token}_{lanes}")
    positions = list(range(1,13))
    if invalid:
        st.warning("Before initializing, complete these items:\n\n" + "\n".join(f"- {item}" for item in blockers))
    if st.button("Confirm Entries and Initialize Event", type="primary", disabled=invalid or not confirmed or bool(selected),
                 help="Apply Remove selected entries first if any entries are ticked for removal."):
        if not name.strip() or not host.strip():
            st.error("Meet name and host/team name are required.")
            return
        event_id = create_event(db_path,name.strip(),host.strip(),start_date.isoformat(),course,lanes,
            meet_type=meet_type,season_year=year,heat_source="generated",run_positions=positions)
        replace_athletes(db_path,event_id,entries)
        st.session_state.event_id = event_id
        st.rerun()


def render(db_path, event_id):
    event, entries = dict(get_event(db_path,event_id)), get_athletes(db_path,event_id)
    from ui.heat_review_tables import review_state, render_workbench
    state = review_state(event, entries)
    pending = state["dirty"]
    st.subheader(f"{event['name']} · Season {event['season_year']}")
    render_event_settings(db_path,event,pending_edits=bool(pending))
    from services.heats import generate_heats, validate_heats, enrich_imported
    from database.repository import save_heat_assignments
    if event["heat_source"]=="imported":
        entries=enrich_imported(entries)
    has_heats=any(a.get("running_heat") or a.get("swimming_heat") for a in entries)
    from services.competition import GENERATION_PROFILES, default_profile
    profile = default_profile(event["meet_type"])
    metadata = json.loads(event.get("generation_metadata") or "{}")
    if event["heat_source"]=="generated":
        st.header("1. Choose a heat generation profile")
        options = list(GENERATION_PROFILES)
        profile = st.selectbox("Heat generation profile",options,
            index=options.index(metadata.get("profile",profile)),
            format_func=lambda value:GENERATION_PROFILES[value].label,
            key=f"generation_profile_{event_id}",disabled=bool(pending))
        st.caption(GENERATION_PROFILES[profile].description)
    if metadata.get("profile") in GENERATION_PROFILES:
        st.caption("Generated using: " + GENERATION_PROFILES[metadata["profile"]].label)
    replace_manual=False
    if event["heat_source"]=="generated":
        st.header("2. Generate heats from entries")
    if has_heats and event["heat_source"]=="generated":
        replace_manual=st.checkbox("Replace current assignments with newly generated heats",key=f"regenerate_{event_id}_{event['heat_revision']}",
            help="Tick this to enable Regenerate heats from entries. Ticking it alone changes nothing. Current heat assignments, including manual changes, are replaced only when you click Regenerate heats from entries.")
    generate_label="Regenerate heats from entries" if has_heats else "Generate heats from entries"
    generate_help="This reruns automatic heat generation and replaces the current heat assignments, including manual changes." if has_heats else None
    if event["heat_source"]=="generated" and st.button(generate_label,type="primary",help=generate_help,disabled=bool(pending) or (has_heats and not replace_manual)):
        try:
            rows = generate_heats(entries,event,profile=profile)
            save_heat_assignments(db_path,event_id,rows,event["heat_revision"],generation_profile=profile)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if event["heat_status"]=="stale":
        st.warning("Assignments changed after approval. Existing operational files are stale; review both disciplines, approve and regenerate them.")
    st.header(("3. " if event["heat_source"]=="generated" else "") +
        ("Organise and confirm heats" if has_heats else "Add, remove or confirm entries"))
    render_workbench(db_path,event,entries,state,has_heats)
    if not has_heats:
        return
    errors,warnings=validate_heats(entries,event)
    if warnings:
        with st.expander(f"Heat notices ({len(warnings)})"):
            for warning in warnings:
                st.write(f"• {warning}")
    for error in errors:
        st.error(error)
    if event["heat_status"]=="approved" and not pending:
        st.success("Both disciplines approved. Operational files use these exact assignments.")
        from ui.phase1_setup import render_operational_outputs
        render_operational_outputs(db_path,event_id)
