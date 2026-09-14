"""Pre-event entry confirmation and run/swim heat review."""
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
import json

import pandas as pd
import streamlit as st

from database.repository import create_event, get_event, get_athletes, replace_athletes, update_event
from database.season_db import init_season_db, season_database_path
from services.seeding import prepare_entries, display_seed, select_seed, time_hundredths
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
    matches = {}
    try:
        entries, ambiguous = prepare_entries(parsed, history_path, year)
    except ValueError as exc:
        st.error(str(exc))
        return
    unresolved = False
    blockers = []
    if ambiguous:
        st.subheader("Check historical identities")
        st.caption("Athletes are linked by athlete number. Name differences are highlighted for reference; the uploaded name is retained.")
    for issue in ambiguous:
        row = issue["entry"]
        if issue.get("number_matched"):
            st.warning(f"{row['athlete_number']}: entry name {row['athlete_name']} differs from historical name {issue['candidates'][0]['athlete_name']}. Linked by athlete number; no action required.")
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
    metadata = pd.DataFrame([{"Athlete": r["athlete_number"], "Name": r["athlete_name"],
        "Age group": r["group_name"], "Gender": r["gender"],
        "Run distance": r["run_distance"], "Swim distance": r["swim_distance"]} for r in entries])
    edited = st.data_editor(metadata, hide_index=True, key=f"entry_metadata_{token}",
        disabled=["Athlete", "Name"], column_config={
            "Gender": st.column_config.SelectboxColumn(options=["F", "M"]),
            "Run distance": st.column_config.NumberColumn(min_value=1, step=1),
            "Swim distance": st.column_config.SelectboxColumn(options=[25,50,100])})
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
                st.warning(f"{entry['athlete_name']}: {discipline} distance {distance} m differs from the category rule ({expected[index]} m). The confirmed event distance will be used.")
            if entry[f"{discipline}_distance"] != distance:
                entry[f"{discipline}_seed"], entry[f"{discipline}_seed_source"] = select_seed(
                    history_path, entry["history_athlete_id"], discipline, distance, year)
            entry[f"{discipline}_distance"] = distance
    st.subheader("Entries and historical seeds")
    st.dataframe([{"Athlete":r["athlete_number"], "Name":r["athlete_name"],
        "Run seed":display_seed(r["run_seed"]), "Run source":seed_source(r,"run"),
        "Swim seed":display_seed(r["swim_seed"]), "Swim source":seed_source(r,"swim")} for r in entries], hide_index=True)
    confirmed = st.checkbox(f"Confirm pool capacity: {lanes} lanes", key=f"confirm_lanes_{token}_{lanes}")
    positions = list(range(1,13))
    if invalid:
        st.warning("Before initializing, complete these items:\n\n" + "\n".join(f"- {item}" for item in blockers))
    if st.button("Confirm Entries and Initialize Event", type="primary", disabled=invalid or not confirmed):
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
    editor_keys={discipline:f"heat_editor_{event_id}_{discipline}_{event['heat_revision']}_{st.session_state.get(f'heat_editor_reset_{event_id}_{discipline}',0)}" for discipline in ("run","swim")}
    carried=st.session_state.get(f"carried_heat_edits_{event_id}",{})
    carried_drafts=carried.get("drafts",{}) if carried.get("revision")==event["heat_revision"] else {}
    drafts={discipline:deepcopy(st.session_state.get(key,{})) for discipline,key in editor_keys.items()}
    for discipline,base in carried_drafts.items():
        merged=deepcopy(base)
        for index,changes in drafts[discipline].get("edited_rows",{}).items():
            merged.setdefault("edited_rows",{}).setdefault(index,{}).update(changes)
        drafts[discipline]=merged
    pending=[discipline for discipline,draft in drafts.items() if draft.get("edited_rows")]
    st.subheader(f"{event['name']} · Season {event['season_year']}")
    if pending:
        st.warning("Unsaved table changes: " + ", ".join(pending) + ". Save the edits beneath the relevant table before moving heats or athletes, reseeding, approving or exporting.")
    render_event_settings(db_path,event,pending_edits=bool(pending))
    st.subheader("Current entries, heats and seeds")
    st.dataframe([{"Athlete":a["athlete_number"],"Name":a["athlete_name"],"Age group":a["group_name"],
        "Run heat":a.get("running_heat"),"Run position":a.get("running_lane"),
        "Swim heat":a.get("swimming_heat"),"Swim lane":a.get("swimming_lane"),
        "Run seed":display_seed(a["run_seed"]),"Run source":seed_source(a,"run"),
        "Swim seed":display_seed(a["swim_seed"]),"Swim source":seed_source(a,"swim")} for a in entries], hide_index=True)
    from services.heats import generate_heats, validate_heats, DISCIPLINES, enrich_imported
    from database.repository import save_heat_assignments, approve_heats
    if event["heat_source"]=="imported":
        entries=enrich_imported(entries)
    has_heats=any(a.get("running_heat") or a.get("swimming_heat") for a in entries)
    replace_manual=False
    if has_heats and event["heat_source"]=="generated":
        st.warning("This reruns automatic heat generation and replaces the current heat assignments, including manual changes.")
        replace_manual=st.checkbox("Replace current assignments with newly generated heats",key=f"regenerate_{event_id}_{event['heat_revision']}")
    generate_label="Regenerate heats from entries" if has_heats else "Generate heats from entries"
    if event["heat_source"]=="generated" and st.button(generate_label, type="primary",disabled=bool(pending) or (has_heats and not replace_manual)):
        try:
            rows = generate_heats(entries,event)
            save_heat_assignments(db_path,event_id,rows,event["heat_revision"])
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if not has_heats:
        return
    if event["heat_status"]=="stale":
        st.warning("Assignments changed after approval. Existing operational files are stale; review both disciplines, approve and regenerate them.")
    for tab,(discipline,prefix) in zip(st.tabs(["Running heats","Swimming heats"]),DISCIPLINES.items()):
        with tab:
            participating=[a for a in entries if a.get(discipline+"_entered") or a.get(prefix+"_heat") is not None]
            if not participating:
                st.info(f"No {discipline} entries.")
                continue
            if discipline=="run" and st.button("Reseed run starting positions",key=f"reseed_run_{event_id}",
                    disabled=bool(pending),
                    help="Number each heat from 1, fastest on the outside. Keeps current heats and replaces run-position overrides."):
                from services.heats import reseed_run_positions
                try:
                    save_heat_assignments(db_path,event_id,reseed_run_positions(entries),event["heat_revision"])
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
            heat_numbers=sorted({a[prefix+"_heat"] for a in participating if a.get(prefix+"_heat") is not None})
            with st.expander("Move an entire heat"):
                if len(heat_numbers)<2:
                    st.caption("At least two heats are needed to change their order.")
                else:
                    moving_heat=st.selectbox("Heat to move",heat_numbers,format_func=lambda value:f"Heat {value}",key=f"move_whole_heat_{discipline}")
                    destination=st.number_input("New place in programme",min_value=1,max_value=len(heat_numbers),
                        value=heat_numbers.index(moving_heat)+1,key=f"whole_heat_position_{event_id}_{discipline}_{moving_heat}_{event['heat_revision']}")
                    st.caption("Moves the whole heat and shifts the others. Heats are renumbered in order; athletes and their lanes stay together.")
                    if st.button("Move entire heat",key=f"apply_whole_heat_{discipline}",disabled=bool(pending) or destination==heat_numbers.index(moving_heat)+1):
                        from services.heats import reorder_heat
                        try:
                            reordered=reorder_heat(entries,discipline,moving_heat,int(destination))
                            save_heat_assignments(db_path,event_id,reordered,event["heat_revision"])
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.rerun()
            with st.expander("Move or swap an athlete"):
                choices={a["athlete_number"]:a for a in participating}
                labels={key:f"{row['athlete_name']} · {row['group_name']} · Heat {row.get(prefix+'_heat') or 'unassigned'} · #{key}"
                    for key,row in choices.items()}
                athlete=st.selectbox("Athlete",list(choices),format_func=labels.get,key=f"move_athlete_{discipline}")
                heat=st.number_input("Move to heat (lower = earlier)",min_value=1,value=int(choices[athlete].get(prefix+"_heat") or 1),key=f"target_heat_{discipline}_{athlete}")
                swap=st.selectbox("Swap with",[None,*[a for a in choices if a!=athlete]],
                    format_func=lambda key, labels=labels:"No swap" if key is None else labels[key],key=f"swap_{discipline}")
                st.caption("Moves and swaps reseed positions in both affected heats." + ("" if discipline=="run" else " Use the table for a manual swim lane override."))
                if st.button("Apply move / swap",key=f"apply_move_{discipline}",disabled=bool(pending)):
                    try:
                        from services.heats import move_or_swap
                        moved=move_or_swap(entries,event,discipline,athlete,int(heat),swap)
                        save_heat_assignments(db_path,event_id,moved,event["heat_revision"])
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()
            st.caption("Edit heat numbers to move athletes earlier/later. Saving recalculates run starting positions from seed times." if discipline=="run" else "Edit heat numbers or lanes, then save before approval.")
            table=pd.DataFrame([{"Athlete":a["athlete_number"],"Name":a["athlete_name"],"Age group":a["group_name"],
                "Gender":a.get("gender"),"Distance":a.get(discipline+"_distance"),"Heat":a.get(prefix+"_heat"),
                "Start position" if discipline=="run" else "Lane":a.get(prefix+"_lane"),
                "Seed":display_seed(a.get(discipline+"_seed")),"Seed source":seed_source(a,discipline)}
                for a in sorted(participating,key=lambda a:(a.get(prefix+"_heat") or 0,a.get(prefix+"_lane") or 0))])
            position_label="Start position" if discipline=="run" else "Lane"
            # Data editors cannot be assigned through session_state. Restore
            # carried edits into their input table instead, keeping them unsaved.
            for index,changes in carried_drafts.get(discipline,{}).get("edited_rows",{}).items():
                for column,value in changes.items():
                    table.at[int(index),column]=value
            st.subheader("Running heat assignments" if discipline=="run" else "Swimming heat assignments")
            edited=st.data_editor(table,hide_index=True,num_rows="fixed",key=editor_keys[discipline],
                disabled=["Athlete","Name","Seed source",*(["Start position"] if discipline=="run" else [])],column_config={
                    "Heat":st.column_config.NumberColumn(min_value=1,step=1),
                    position_label:st.column_config.NumberColumn(min_value=1,step=1),
                    "Gender":st.column_config.SelectboxColumn(options=["F","M"]),
                    "Distance":st.column_config.NumberColumn(min_value=1,step=1)})
            save_label="Save run heats and recalculate starting positions" if discipline=="run" else "Save swim heat edits"
            if st.button(save_label,key=f"save_heats_{discipline}"):
                try:
                    changes={r["Athlete"]:r for _,r in edited.iterrows()}
                    for entry in entries:
                        if entry["athlete_number"] not in changes:
                            continue
                        row=changes[entry["athlete_number"]]
                        old_distance=entry.get(discipline+"_distance")
                        old_seed=entry.get(discipline+"_seed")
                        for label,field in (("Heat",prefix+"_heat"),(position_label,prefix+"_lane"),("Distance",discipline+"_distance")):
                            if pd.isna(row[label]) or float(row[label])!=int(row[label]):
                                raise ValueError(f"{label} requires a whole number.")
                            entry[field]=int(row[label])
                        entry["group_name"],entry["gender"]=str(row["Age group"]),str(row["Gender"])
                        text=str(row["Seed"]).strip()
                        value=None if text.upper() in {"","NT"} else time_hundredths(text)
                        if value is None and text.upper() not in {"","NT"}:
                            raise ValueError("Enter a valid seed time such as 01:20.50, or NT.")
                        if entry.get(discipline+"_distance")!=old_distance and value==old_seed:
                            value=None
                            entry[discipline+"_seed_source"]="NT - distance changed; select a valid seed or override explicitly"
                        if value!=entry.get(discipline+"_seed"):
                            entry[discipline+"_seed"],entry[discipline+"_seed_source"]=value,"Manual override"
                    if discipline=="run":
                        from services.heats import reseed_run_positions
                        entries=reseed_run_positions(entries)
                    errors,_=validate_heats(entries,event)
                    if errors:
                        raise ValueError("\n".join(errors))
                    save_heat_assignments(db_path,event_id,entries,event["heat_revision"])
                    # Saving one discipline advances the shared revision. Carry
                    # the other table's unsaved delta to its new widget key.
                    revision=get_event(db_path,event_id)["heat_revision"]
                    st.session_state[f"carried_heat_edits_{event_id}"]={"revision":revision,
                        "drafts":{other:drafts[other] for other in pending if other!=discipline}}
                    reset_key=f"heat_editor_reset_{event_id}_{discipline}"
                    st.session_state[reset_key]=st.session_state.get(reset_key,0)+1
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
    errors,warnings=validate_heats(entries,event)
    if warnings:
        with st.expander(f"Heat notices ({len(warnings)})"):
            for warning in warnings:
                st.write(f"• {warning}")
    for error in errors:
        st.error(error)
    if event["heat_status"]!="approved":
        reviewed_run=st.checkbox("I have reviewed the running heats",key=f"review_run_{event_id}_{event['heat_revision']}")
        reviewed_swim=st.checkbox("I have reviewed the swimming heats",key=f"review_swim_{event_id}_{event['heat_revision']}")
        if st.button("Approve final run and swim heats",type="primary",disabled=bool(pending) or bool(errors) or not(reviewed_run and reviewed_swim)):
            save_heat_assignments(db_path,event_id,entries,event["heat_revision"])
            approve_heats(db_path,event_id,get_event(db_path,event_id)["heat_revision"])
            st.rerun()
    elif not pending:
        st.success("Both disciplines approved. Operational files use these exact assignments.")
        from ui.phase1_setup import render_operational_outputs
        render_operational_outputs(db_path,event_id)
