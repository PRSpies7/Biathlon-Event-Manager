"""Batch review: one form submits both disciplines without per-cell reruns."""
from copy import deepcopy
from pathlib import Path
import pandas as pd
import streamlit as st
from database.repository import get_event, save_heat_assignments, save_review_roster, approve_heats
from database.season_db import init_season_db, season_database_path
from services.heats import DISCIPLINES, apply_heat_programme, combine_selected_heats, validate_heats
from services.seeding import display_seed, time_hundredths, duplicate_names, prepare_late_entry


def _athlete_rows(entries, discipline):
    prefix = DISCIPLINES[discipline]
    participating = [a for a in entries if a.get(discipline+"_entered") or a.get(prefix+"_heat") is not None]
    return [{"Athlete":a["athlete_number"],"Name":a["athlete_name"],"Age group":a["group_name"],
             "Gender":a.get("gender"),"Distance":a.get(discipline+"_distance"),"Heat":a.get(prefix+"_heat"),
             **({"Lane":a.get(prefix+"_lane")} if discipline=="swim" else {}),
             "Seed":display_seed(a.get(discipline+"_seed")),"Remove from event":False}
            for a in sorted(participating,key=lambda a:(a.get(prefix+"_heat") or 0,a.get(prefix+"_lane") or 0))]


def _new_draft(entries, discipline, programme=None):
    athletes = _athlete_rows(entries,discipline)
    heats = sorted({a["Heat"] for a in athletes if a["Heat"] is not None})
    return {"athletes":athletes,"programme":programme if programme is not None else
            [{"Heat":h,"New Position":i,"Combine":False} for i,h in enumerate(heats,1)]}


def review_state(event, entries):
    key = f"heat_review_tables_{event['id']}"
    state = st.session_state.get(key)
    if state is not None and "rows" not in state:
        state = None  # Upgrade the earlier local prototype's draft format.
    if state is not None and state["revision"] != event["heat_revision"]:
        if state["dirty"]:
            st.warning("The saved event changed while these edits were pending. Reload before continuing.")
            if st.button("Reload saved heats and discard drafts",key=f"reload_heat_drafts_{event['id']}"):
                del st.session_state[key]
                st.rerun()
            st.stop()
        state = None
    if state is None:
        state = {"revision":event["heat_revision"],"rows":deepcopy(entries),"dirty":False,"version":0,
                 "drafts":{d:_new_draft(entries,d) for d in DISCIPLINES},"lane_overrides":set()}
        st.session_state[key] = state
    return state


def duplicate_name_notices(rows, only_numbers=None):
    notices = []
    for group in duplicate_names(rows):
        if only_numbers is not None and not any(r["athlete_number"] in only_numbers for r in group):
            continue
        details = "; ".join(f"#{r['athlete_number']} ({r.get('group_name') or 'no category'})" for r in group)
        notices.append(f"Same full name: {group[0]['athlete_name']} — {details}. Check whether these are separate people or an incorrect entry.")
    return notices


def show_entry_notices(notices):
    if notices:
        label = f"{len(notices)} potential {'issue' if len(notices)==1 else 'issues'} found"
        with st.expander(label):
            for notice in notices:
                st.warning(notice)


def _whole_number(value, label):
    if pd.isna(value) or isinstance(value,bool) or float(value)!=int(value) or int(value)<1:
        raise ValueError(f"{label} requires a positive whole number.")
    return int(value)


def _reorder_programme(original, edited, athletes):
    programme = deepcopy(edited)
    known = {p["Heat"] for p in programme}
    for row in athletes:
        heat = _whole_number(row["Heat"],"Heat")
        if heat not in known:
            programme.append({"Heat":heat,"New Position":len(programme)+1,"Combine":False})
            known.add(heat)
    before = {p["Heat"]:p["New Position"] for p in original}
    targets = {p["Heat"]:_whole_number(p["New Position"],"New Position") for p in programme
               if p.pop("_position_edited",False) or p["New Position"]!=before.get(p["Heat"],p["New Position"])}
    if len(set(targets.values()))!=len(targets) or any(p>len(programme) for p in targets.values()):
        raise ValueError("New positions must be different and within the heat programme.")
    placed = {targets[p["Heat"]]:p for p in programme if p["Heat"] in targets}
    remaining = iter(p for p in programme if p["Heat"] not in targets)
    result = [placed[i] if i in placed else next(remaining) for i in range(1,len(programme)+1)]
    for i,p in enumerate(result,1):
        p["New Position"] = i
    return result


def _collect(state, tables, has_heats):
    """Capture both form tables together. Database writes happen only on save."""
    working = deepcopy(state)
    rows = {a["athlete_number"]:a for a in working["rows"]}
    removed = {r["Athlete"] for _,athletes in tables.values() for r in athletes if r["Remove from event"]}
    for discipline,(programme,athletes) in tables.items():
        baseline = {r["Athlete"]:r for r in state["drafts"][discipline]["athletes"]}
        prefix = DISCIPLINES[discipline]
        for edited in athletes:
            number = edited["Athlete"]
            if number in removed:
                continue
            row = rows[number]
            if has_heats:
                row[prefix+"_heat"] = _whole_number(edited["Heat"],"Heat")
            distance = _whole_number(edited["Distance"],"Distance")
            text = str(edited["Seed"]).strip()
            seed = None if text.upper() in {"","NT"} else time_hundredths(text)
            if seed is None and text.upper() not in {"","NT"}:
                raise ValueError("Enter a valid seed such as 01:20.50, or NT.")
            if distance!=row.get(discipline+"_distance") and seed==row.get(discipline+"_seed"):
                seed = None
            if seed!=row.get(discipline+"_seed"):
                row[discipline+"_seed"],row[discipline+"_seed_source"] = seed,"Manual override"
            row[discipline+"_distance"] = distance
            for label,field in (("Age group","group_name"),("Gender","gender")):
                if edited[label]!=baseline[number][label]:
                    row[field] = str(edited[label])
            if discipline=="swim" and has_heats:
                row["swimming_lane"] = _whole_number(edited["Lane"],"Lane")
                if edited["Lane"]!=baseline[number]["Lane"]:
                    working["lane_overrides"].add(number)
        working["drafts"][discipline]["programme"] = (_reorder_programme(
            state["drafts"][discipline]["programme"],programme,[r for r in athletes if not r["Remove from event"]]) if has_heats else [])
    working["rows"] = [r for n,r in rows.items() if n not in removed]
    for d in DISCIPLINES:
        working["drafts"][d] = _new_draft(working["rows"],d,working["drafts"][d]["programme"])
    working["dirty"] = True
    working["version"] += 1
    return working


def _remember_tab(event_id, label):
    st.session_state[f"heat_review_active_{event_id}"] = label
    st.session_state[f"heat_review_tabs_{event_id}"] = label


def _save(db_path,event,previous,working,has_heats):
    rows = working["rows"]
    old = {r["athlete_number"] for r in previous}
    new = {r["athlete_number"] for r in rows}
    reference = [r for r in previous if r["athlete_number"] in new]
    reference += [dict(r,running_heat=None,swimming_heat=None) for r in rows if r["athlete_number"] not in old]
    if has_heats:
        for d in DISCIPLINES:
            rows = apply_heat_programme(rows,reference,event,d,working["drafts"][d]["programme"],working["lane_overrides"],validate=False)
        errors,_ = validate_heats(rows,event)
        if errors:
            raise ValueError("\n".join(errors))
    if old!=new:
        save_review_roster(db_path,event["id"],rows,working["revision"],added=new-old,removed=old-new)
    else:
        save_heat_assignments(db_path,event["id"],rows,working["revision"])


def render_workbench(db_path,event,entries,state,has_heats):
    state_key = f"heat_review_tables_{event['id']}"
    added = {r["athlete_number"] for r in state["rows"]}-{r["athlete_number"] for r in entries}
    show_entry_notices(duplicate_name_notices(state["rows"],only_numbers=added))
    save_label = "Save heat changes" if has_heats else "Save entry changes"
    if state["dirty"]:
        st.info(f"Changes are pending. {save_label} to apply them, or discard them.")
    action, tables = None, {}
    labels = ["Running heats","Swimming heats"] if has_heats else ["Running entries","Swimming entries"]
    with st.form(f"heat_review_form_{event['id']}",enter_to_submit=False):
        tabs = st.tabs(labels,key=f"heat_review_tabs_{event['id']}",on_change="rerun")
        for tab,(discipline,prefix),label in zip(tabs,DISCIPLINES.items(),labels):
            with tab:
                draft = state["drafts"][discipline]
                suffix = f"{event['id']}_{discipline}_{state['revision']}_{state['version']}"
                if has_heats:
                    st.subheader(f"{prefix.title()} heat programme")
                    summary = [dict(p,Athletes=sum(a["Heat"]==p["Heat"] for a in draft["athletes"]),
                        Categories=", ".join(sorted({a["Age group"] for a in draft["athletes"] if a["Heat"]==p["Heat"]}))) for p in draft["programme"]]
                    programme = st.data_editor(pd.DataFrame(summary,columns=["Heat","New Position","Categories","Athletes","Combine"]),
                        key=f"programme_editor_{suffix}",hide_index=True,num_rows="fixed",width="content",
                        disabled=["Heat","Athletes","Categories"],column_config={
                            "Heat":st.column_config.NumberColumn(width=64),
                            "New Position":st.column_config.NumberColumn(width=112,min_value=1,step=1,help="Move this whole heat here when applying changes."),
                            "Categories":st.column_config.TextColumn(width=320),
                            "Athletes":st.column_config.NumberColumn(width=88),
                            "Combine":st.column_config.CheckboxColumn(width=88,help="Select two or more heats, then click Combine. Only selected heats are rebuilt.")}).to_dict("records")
                    for index,changes in st.session_state.get(f"programme_editor_{suffix}",{}).get("edited_rows",{}).items():
                        if "New Position" in changes:
                            programme[int(index)]["_position_edited"] = True
                    with st.container(horizontal=True):
                        if st.form_submit_button("Combine",key=f"combine_heats_{discipline}",on_click=_remember_tab,args=(event["id"],label)):
                            action = ("combine",discipline)
                        if st.form_submit_button("Add heat",key=f"add_heat_{discipline}",on_click=_remember_tab,args=(event["id"],label)):
                            action = ("add_heat",discipline)
                else:
                    programme = []
                st.subheader(f"{prefix.title()} heat assignments" if has_heats else f"{prefix.title()} entries")
                if draft["athletes"]:
                    columns = [c for c in draft["athletes"][0] if has_heats or c not in {"Heat","Lane"}]
                    athletes = st.data_editor(pd.DataFrame(draft["athletes"]),key=f"heat_editor_{suffix}",hide_index=True,
                        num_rows="fixed",column_order=columns,disabled=["Athlete","Name"],column_config={
                            "Heat":st.column_config.NumberColumn(min_value=1,step=1),
                            "Lane":st.column_config.NumberColumn(min_value=1,step=1),
                            "Distance":st.column_config.NumberColumn(min_value=1,step=1),
                            "Gender":st.column_config.SelectboxColumn(options=["F","M"]),
                            "Remove from event":st.column_config.CheckboxColumn(help="Removes this entry from BOTH disciplines on save. Historical results are not deleted.")}).to_dict("records")
                else:
                    st.info("No athletes entered in this discipline.")
                    athletes = []
                tables[discipline] = (programme,athletes)
                if st.form_submit_button(save_label,key=f"save_heats_{discipline}",type="primary",
                    on_click=_remember_tab,args=(event["id"],label),help="Saves both disciplines and roster edits." + (" Empty heats disappear and numbering gaps close." if has_heats else "")):
                    action = ("save",discipline)
        with st.expander("Add athlete to this event"):
            number = st.text_input("Athlete number",key=f"late_number_{event['id']}")
            name = st.text_input("Full name",key=f"late_name_{event['id']}")
            category = st.selectbox("Age category",["U/08","U/09","U/11","U/13","U/15","U/17","U/19","JNR","SENIOR",
                "MASTERS 40+","MASTERS 50+","MASTERS 60+","MASTERS 70+","MASTERS 80+","SPECIAL NEEDS"],key=f"late_category_{event['id']}")
            gender = st.selectbox("Gender",["F","M"],key=f"late_gender_{event['id']}")
            run = st.checkbox("Enter running",value=True,key=f"late_run_{event['id']}")
            swim = st.checkbox("Enter swimming",value=True,key=f"late_swim_{event['id']}")
            if st.form_submit_button("Add athlete",key=f"add_athlete_{event['id']}"):
                action = ("add_athlete",None)
        if st.form_submit_button("Discard unsaved changes",key=f"discard_heats_{event['id']}"):
            action = ("discard",None)
        if has_heats and event["heat_status"]!="approved":
            reviewed_run = st.checkbox("I have reviewed the running heats",key=f"review_run_{event['id']}_{event['heat_revision']}")
            reviewed_swim = st.checkbox("I have reviewed the swimming heats",key=f"review_swim_{event['id']}_{event['heat_revision']}")
            if st.form_submit_button("Approve final run and swim heats",key=f"approve_heats_{event['id']}"):
                action = ("approve",None)
    if action is None:
        return
    kind,discipline = action
    if kind=="discard":
        del st.session_state[state_key]
        st.rerun()
    try:
        working = _collect(state,tables,has_heats)
        if kind=="add_heat":
            programme = working["drafts"][discipline]["programme"]
            heat = max((p["Heat"] for p in programme),default=0)+1
            programme.append({"Heat":heat,"New Position":len(programme)+1,"Combine":False})
        elif kind=="combine":
            programme = working["drafts"][discipline]["programme"]
            selected = {p["Heat"] for p in programme if p["Combine"]}
            involved = {r["athlete_number"] for r in working["rows"] if r.get(DISCIPLINES[discipline]+"_heat") in selected}
            working["rows"],programme = combine_selected_heats(working["rows"],event,discipline,programme,selected)
            if discipline=="swim":
                working["lane_overrides"] -= involved
            working["drafts"][discipline] = _new_draft(working["rows"],discipline,programme)
        elif kind=="add_athlete":
            history = season_database_path(Path(__file__).resolve().parents[1])
            init_season_db(history)
            row = prepare_late_entry(working["rows"],event,history,number,name,category,gender,run,swim)
            if not has_heats:
                row.update(running_heat=None,running_lane=None,swimming_heat=None,swimming_lane=None)
            working["rows"].append(row)
            for d in DISCIPLINES:
                programme = working["drafts"][d]["programme"]
                heat = row.get(DISCIPLINES[d]+"_heat")
                if heat is not None:
                    programme.append({"Heat":heat,"New Position":len(programme)+1,"Combine":False})
                working["drafts"][d] = _new_draft(working["rows"],d,programme)
        elif kind in {"save","approve"}:
            if kind=="approve" and not (reviewed_run and reviewed_swim):
                raise ValueError("Confirm review of both disciplines before approval.")
            _save(db_path,event,entries,working,has_heats)
            if kind=="approve":
                approve_heats(db_path,event["id"],get_event(db_path,event["id"])["heat_revision"])
            del st.session_state[state_key]
            st.rerun()
        st.session_state[state_key] = working
    except (ValueError,TypeError,OverflowError) as exc:
        st.error(str(exc))
    else:
        st.rerun()
