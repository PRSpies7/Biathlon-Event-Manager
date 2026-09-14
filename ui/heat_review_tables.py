"""Linked programme/athlete drafts; database writes happen only on explicit save."""
from copy import deepcopy

import pandas as pd
import streamlit as st

from database.repository import get_event, save_heat_assignments
from services.heats import DISCIPLINES, apply_heat_programme
from services.seeding import display_seed, time_hundredths


def _athlete_rows(entries, discipline):
    prefix = DISCIPLINES[discipline]
    participating = [a for a in entries if a.get(discipline+"_entered") or a.get(prefix+"_heat") is not None]
    return [{"Athlete": a["athlete_number"], "Name": a["athlete_name"], "Age group": a["group_name"],
             "Gender": a.get("gender"), "Distance": a.get(discipline+"_distance"),
             "Heat": a.get(prefix+"_heat"),
             "Start position" if discipline == "run" else "Lane": a.get(prefix+"_lane"),
             "Seed": display_seed(a.get(discipline+"_seed")),
             "Seed source": "NT" if a.get(discipline+"_seed") is None else a.get(discipline+"_seed_source") or "Manual override"}
            for a in sorted(participating, key=lambda a: (a.get(prefix+"_heat") or 0, a.get(prefix+"_lane") or 0))]


def _new_draft(entries, discipline, version=0):
    athletes = _athlete_rows(entries, discipline)
    heats = sorted({a["Heat"] for a in athletes if a["Heat"] is not None})
    return {"athletes": athletes, "baseline": deepcopy(athletes),
            "programme": [{"Heat": heat, "Programme position": i, "Delete": False} for i, heat in enumerate(heats, 1)],
            "dirty": False, "version": version, "programme_error": None, "lane_overrides": set()}


def review_state(event, entries):
    key = f"heat_review_tables_{event['id']}"
    state = st.session_state.get(key)
    if state is not None and state["revision"] != event["heat_revision"]:
        if any(d["dirty"] for d in state["drafts"].values()):
            st.warning("The saved event changed while these table edits were pending. Reload the saved heats before continuing.")
            if st.button("Reload saved heats and discard drafts", key=f"reload_heat_drafts_{event['id']}"):
                del st.session_state[key]
                st.rerun()
            st.stop()
        state = None
    if state is None:
        state = {"revision": event["heat_revision"],
                 "drafts": {discipline: _new_draft(entries, discipline) for discipline in DISCIPLINES}}
        st.session_state[key] = state
    return state


def _whole_number(value, label):
    if pd.isna(value) or isinstance(value, bool) or float(value) != int(value) or int(value) < 1:
        raise ValueError(f"{label} requires a positive whole number.")
    return int(value)


def _positions(programme):
    for index, row in enumerate(programme, 1):
        row["Programme position"] = index


def _capture_editor(state_key, discipline, kind, widget_key):
    """Fold one editor delta into the shared draft, then give both fresh keys.

    The programme can update counts/order without resetting athlete edits. Heat
    IDs stay stable during editing; only the final save assigns new heat numbers.
    """
    draft = st.session_state[state_key]["drafts"][discipline]
    delta = st.session_state[widget_key].get("edited_rows", {})
    moves = []
    for index, changes in delta.items():
        row = draft[kind][int(index)]
        row.update(changes)
        if kind == "programme" and "Programme position" in changes:
            moves.append((row["Heat"], changes["Programme position"]))
        if kind == "athletes" and "Lane" in changes:
            draft["lane_overrides"].add(row["Athlete"])
    if moves:
        try:
            targets = [(heat, _whole_number(value, "Programme position")) for heat, value in moves]
            if any(position > len(draft["programme"]) for _, position in targets):
                raise ValueError("Programme position must be within the current heat list.")
            if len({position for _, position in targets}) != len(targets):
                raise ValueError("Choose different programme positions for the heats being moved.")
            # Place all explicitly requested positions together (including pasted
            # multi-row edits), then fill gaps with the other heats in old order.
            requested = dict(targets)
            positioned = {requested[p["Heat"]]: p for p in draft["programme"] if p["Heat"] in requested}
            remaining = iter(p for p in draft["programme"] if p["Heat"] not in requested)
            draft["programme"] = [positioned[i] if i in positioned else next(remaining)
                                  for i in range(1, len(draft["programme"])+1)]
            _positions(draft["programme"])
            draft["programme_error"] = None
        except (TypeError, ValueError, OverflowError) as exc:
            draft["programme_error"] = str(exc)
    if kind == "athletes":
        known = {p["Heat"] for p in draft["programme"]}
        for row in draft["athletes"]:
            try:
                heat = _whole_number(row["Heat"], "Heat")
            except (TypeError, ValueError, OverflowError):
                continue  # Keep invalid input visible until corrected or discarded.
            if heat not in known:
                draft["programme"].append({"Heat": heat, "Programme position": len(draft["programme"])+1, "Delete": False})
                known.add(heat)
    draft["dirty"] = True
    draft["version"] += 1


def _edited_entries(entries, draft, discipline):
    rows = deepcopy(entries)
    changes = {r["Athlete"]: r for r in draft["athletes"]}
    prefix = DISCIPLINES[discipline]
    for entry in rows:
        if entry["athlete_number"] not in changes:
            continue
        row = changes[entry["athlete_number"]]
        old_distance, old_seed = entry.get(discipline+"_distance"), entry.get(discipline+"_seed")
        for label, field in (("Heat", prefix+"_heat"), ("Distance", discipline+"_distance")):
            entry[field] = _whole_number(row[label], label)
        if discipline == "swim":
            entry[prefix+"_lane"] = _whole_number(row["Lane"], "Lane")
        entry["group_name"], entry["gender"] = str(row["Age group"]), str(row["Gender"])
        text = str(row["Seed"]).strip()
        value = None if text.upper() in {"", "NT"} else time_hundredths(text)
        if value is None and text.upper() not in {"", "NT"}:
            raise ValueError("Enter a valid seed time such as 01:20.50, or NT.")
        if entry[discipline+"_distance"] != old_distance and value == old_seed:
            value = None
            entry[discipline+"_seed_source"] = "NT - distance changed; select a valid seed or override explicitly"
        if value != old_seed:
            entry[discipline+"_seed"], entry[discipline+"_seed_source"] = value, "Manual override"
    return rows


def _refresh_other_draft(draft, entries, discipline):
    """Rebase unchanged cells after the other discipline saves shared metadata."""
    fresh = {r["Athlete"]: r for r in _athlete_rows(entries, discipline)}
    original = {r["Athlete"]: r for r in draft["baseline"]}
    for row in draft["athletes"]:
        for column, value in fresh[row["Athlete"]].items():
            if row[column] == original[row["Athlete"]][column]:
                row[column] = value
    draft["baseline"] = [fresh[r["Athlete"]] for r in draft["athletes"]]
    draft["version"] += 1


def render_tables(db_path, event, entries, discipline, state):
    state_key = f"heat_review_tables_{event['id']}"
    draft = state["drafts"][discipline]
    title = DISCIPLINES[discipline].title()
    st.subheader(f"{title} heat programme")
    with st.container(horizontal=True):
        if st.button("Add heat", key=f"add_heat_{discipline}",
                     help="Adds an empty draft heat. Assign athletes to its Heat number below before saving."):
            heat = max((p["Heat"] for p in draft["programme"]), default=0)+1
            draft["programme"].append({"Heat": heat, "Programme position": len(draft["programme"])+1, "Delete": False})
            draft["dirty"] = True
            draft["version"] += 1
            st.rerun()
        if st.button("Discard unsaved changes", key=f"discard_heats_{discipline}", disabled=not draft["dirty"]):
            state["drafts"][discipline] = _new_draft(entries, discipline, draft["version"]+1)
            st.rerun()
    summary = []
    for row in draft["programme"]:
        members = [a for a in draft["athletes"] if a["Heat"] == row["Heat"]]
        summary.append({"Heat": row["Heat"], "Programme position": row["Programme position"],
                        "Athletes": len(members), "Categories": ", ".join(sorted({str(a["Age group"]) for a in members})),
                        "Delete": row["Delete"]})
    suffix = f"{event['id']}_{discipline}_{state['revision']}_{draft['version']}"
    programme_key = f"programme_editor_{suffix}"
    st.data_editor(pd.DataFrame(summary), key=programme_key, hide_index=True, num_rows="fixed",
                   disabled=["Heat", "Athletes", "Categories"],
                   column_config={"Programme position": st.column_config.NumberColumn(min_value=1, step=1,
                       help="Move the whole heat to this position; the others shift. Heat numbers update on save."),
                       "Delete": st.column_config.CheckboxColumn(help="A heat can be deleted only once all its athletes have been moved out.")},
                   on_change=_capture_editor, args=(state_key, discipline, "programme", programme_key))
    if draft["programme_error"]:
        st.error(draft["programme_error"])
    st.caption("Use Heat numbers below to move athletes. Save applies both tables, removes empty heats and closes numbering gaps.")
    st.subheader(f"{title} heat assignments")
    athlete_key = f"heat_editor_{suffix}"
    position_label = "Start position" if discipline == "run" else "Lane"
    st.data_editor(pd.DataFrame(draft["athletes"]), key=athlete_key, hide_index=True, num_rows="fixed",
                   disabled=["Athlete", "Name", "Seed source", *(["Start position"] if discipline == "run" else [])],
                   column_config={"Heat": st.column_config.NumberColumn(min_value=1, step=1),
                       position_label: st.column_config.NumberColumn(min_value=1, step=1),
                       "Gender": st.column_config.SelectboxColumn(options=["F", "M"]),
                       "Distance": st.column_config.NumberColumn(min_value=1, step=1)},
                   on_change=_capture_editor, args=(state_key, discipline, "athletes", athlete_key))
    if st.button("Save heat changes", key=f"save_heats_{discipline}", type="primary",
                 help="Saves both tables for this discipline. Run positions are recalculated from 1. Changed swim heats are reseeded, preserving explicit lane edits."):
        try:
            if draft["programme_error"]:
                raise ValueError(draft["programme_error"])
            rows = _edited_entries(entries, draft, discipline)
            rows = apply_heat_programme(rows, entries, event, discipline, draft["programme"], draft["lane_overrides"])
            save_heat_assignments(db_path, event["id"], rows, state["revision"])
            state["revision"] = get_event(db_path, event["id"])["heat_revision"]
            for other in DISCIPLINES:
                if other == discipline or not state["drafts"][other]["dirty"]:
                    state["drafts"][other] = _new_draft(rows, other, state["drafts"][other]["version"]+1)
                else:
                    _refresh_other_draft(state["drafts"][other], rows, other)
        except (TypeError, ValueError, OverflowError) as exc:
            st.error(str(exc))
        else:
            st.rerun()
