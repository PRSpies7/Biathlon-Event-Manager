from __future__ import annotations

import pandas as pd
import streamlit as st

from database.repository import (
    add_athlete_to_run_heat,
    assign_athlete_to_run_heat,
    get_athletes,
    get_run_groups,
    get_running_heats,
    remove_athlete_from_run_heat,
    restore_run_position_mappings,
    save_run_positions,
)
from exporters.run_positions import build_run_positions_xlsx
from parsers.run_positions_excel import parse_run_positions_excel
from validation.validators import validate_positions


def _selected_key(selected: list[int]) -> str:
    return "+".join(map(str, selected))


def _read_editor_positions(athletes: list[dict], selected: list[int], editor_key: str) -> dict[str, int | None]:
    """Read the current Phase 2 data-editor state, including edits made immediately before navigation."""
    positions: dict[str, int | None] = {
        str(a["athlete_number"]): (int(a["run_position"]) if a.get("run_position") is not None else None)
        for a in athletes
    }
    state = st.session_state.get(editor_key, {})
    for row_idx, changes in state.get("edited_rows", {}).items():
        try:
            athlete = athletes[int(row_idx)]
        except (IndexError, TypeError, ValueError):
            continue
        if "Position" not in changes:
            continue
        raw = changes.get("Position")
        text = "" if raw is None else str(raw).strip()
        if not text:
            positions[str(athlete["athlete_number"])] = None
        else:
            try:
                positions[str(athlete["athlete_number"])] = int(text)
            except ValueError:
                positions[str(athlete["athlete_number"])] = -1
    return positions


def _navigation_units(heats: list[int], run_groups: list[dict]) -> list[list[int]]:
    """Return ordered navigation units: persisted combined groups plus uncompleted singleton heats."""
    heat_to_group: dict[int, list[int]] = {}
    valid_groups: list[list[int]] = []
    for group in run_groups:
        nums = sorted({int(n) for n in group.get("heat_numbers", []) if int(n) in heats})
        if not nums:
            continue
        # A heat belongs to one persisted group. Ignore malformed overlaps safely.
        if any(n in heat_to_group for n in nums):
            continue
        valid_groups.append(nums)
        for n in nums:
            heat_to_group[n] = nums

    units = [list(g) for g in valid_groups]
    units.extend([[h] for h in heats if h not in heat_to_group])
    units.sort(key=lambda g: (min(g), tuple(g)))
    return units


def _unit_for_heat(heat: int, units: list[list[int]]) -> list[int]:
    for unit in units:
        if heat in unit:
            return unit
    return [heat]


def _unit_index(selected: list[int], units: list[list[int]]) -> int:
    target = tuple(sorted(selected))
    for i, unit in enumerate(units):
        if tuple(unit) == target:
            return i
    return next((i for i, unit in enumerate(units) if set(unit) == set(selected)), 0)


def _label(unit: list[int], total_heats: int) -> str:
    if len(unit) > 1:
        return " + ".join(f"Heat {n}" for n in unit)
    return f"Heat {unit[0]} of {total_heats}"


def save_current_mapping(db_path: str, event_id: int) -> list[str]:
    """Persist the visible Phase 2 mapping before the application changes phase."""
    athletes = get_athletes(db_path, event_id)
    heats = get_running_heats(db_path, event_id)
    run_groups = get_run_groups(db_path, event_id)
    if not heats:
        return []

    current_heat = int(st.session_state.get(f"phase2_heat_{event_id}", min(heats)))
    current_unit = _unit_for_heat(current_heat, _navigation_units(heats, run_groups))
    combine_key = f"phase2_combine_{event_id}_{_selected_key(current_unit)}"
    selected = sorted({int(x) for x in st.session_state.get(combine_key, current_unit)})
    if not selected:
        return ["Select at least one heat before continuing."]
    if len(selected) > 1 and not st.session_state.get(
        f"confirm_combined_{event_id}_{_selected_key(selected)}", False
    ):
        return ["Confirm the combined heats before continuing."]

    current = sorted(
        [a for a in athletes if a.get("running_heat") in selected],
        key=lambda a: a["sort_order"],
    )
    positions = _read_editor_positions(
        current, selected, f"phase2_editor_{event_id}_{_selected_key(selected)}"
    )
    issues = validate_positions(current, positions)
    if issues:
        return issues
    save_run_positions(db_path, event_id, selected, positions)
    return []


def _render_compact_athlete_controls(db_path: str, event_id: int, athletes: list[dict], selected: list[int]) -> None:
    """Render compact run-heat athlete controls below the position table."""
    if len(selected) != 1:
        st.caption("Select one run heat to add an athlete.")
        return

    heat = selected[0]
    lookup_key = f"phase2_add_athlete_{event_id}_{heat}"
    pending_key = f"phase2_new_athlete_{event_id}_{heat}"
    assigned = [a for a in athletes if a.get("running_heat") == heat]
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="bottom"):
        lookup = st.text_input(
            "Add athlete",
            key=lookup_key,
            placeholder="Insert Athlete Number or Exact Athlete Name",
            label_visibility="collapsed",
            width=340,
        ).strip()
        add_clicked = st.button(
            "Add to Heat",
            width=160,
            key=f"phase2_add_btn_{event_id}_{heat}",
        )
    with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="bottom"):
        remove_number = st.selectbox(
            "Athlete to remove from run heat",
            options=[str(a["athlete_number"]) for a in assigned],
            index=None,
            format_func=lambda number: next(
                f"{a['athlete_name']} ({a['athlete_number']})"
                for a in assigned if str(a["athlete_number"]) == number
            ),
            placeholder="Select athlete to remove",
            label_visibility="collapsed",
            width=340,
            key=f"phase2_remove_athlete_{event_id}_{heat}",
        )
        remove_clicked = st.button(
            "Remove from Heat",
            width=160,
            disabled=remove_number is None,
            key=f"phase2_remove_btn_{event_id}_{heat}",
        )

    if remove_clicked and remove_number is not None:
        try:
            changed = remove_athlete_from_run_heat(db_path, event_id, remove_number, selected)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if changed:
                st.success(f"Athlete {remove_number} removed from Heat {heat}. The athlete remains in the event.")
                st.rerun()
            st.info("That athlete does not currently have a run heat assignment.")

    if add_clicked:
        by_number = [a for a in athletes if str(a["athlete_number"]).strip() == lookup]
        by_name = [
            a for a in athletes
            if " ".join(str(a["athlete_name"]).split()).casefold()
            == " ".join(lookup.split()).casefold()
        ] if lookup and not by_number else []
        matches = by_number or by_name
        if not lookup:
            st.error("Enter an athlete number or exact athlete name.")
        elif len(matches) > 1:
            st.error("That athlete name is ambiguous. Enter the athlete number instead.")
        elif matches:
            athlete = matches[0]
            try:
                changed = assign_athlete_to_run_heat(db_path, event_id, athlete["athlete_number"], heat)
            except ValueError as exc:
                st.error(str(exc))
            else:
                if changed:
                    st.success(f"Athlete {athlete['athlete_number']} moved to Heat {heat}.")
                    st.rerun()
                st.info("That athlete is already assigned to this heat.")
        elif lookup.isdecimal():
            st.session_state[pending_key] = lookup
            st.rerun()
        else:
            st.error("No athlete matches that name. A new athlete must be added with an athlete number.")

    athlete_number = st.session_state.get(pending_key)
    if athlete_number:
        st.caption(
            f"Athlete number {athlete_number} is not currently recorded. Confirm the number, then enter the athlete name."
        )
        with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="bottom"):
            athlete_name = st.text_input(
                "New athlete name",
                key=f"phase2_new_athlete_name_{event_id}_{heat}",
                placeholder="Athlete name",
                label_visibility="collapsed",
                width=340,
            )
            confirmed = st.button("Confirm", key=f"phase2_new_athlete_confirm_{event_id}_{heat}")
            cancelled = st.button("Cancel", key=f"phase2_new_athlete_cancel_{event_id}_{heat}")
        if cancelled:
            st.session_state.pop(pending_key, None)
            st.rerun()
        if confirmed:
            try:
                add_athlete_to_run_heat(db_path, event_id, athlete_number, athlete_name, heat)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop(pending_key, None)
                st.success(f"Athlete {athlete_number} added to Heat {heat}.")
                st.rerun()


def render(db_path: str, event_id: int):
    st.header("Phase 2 · Run Position Mapping")
    for issue in st.session_state.pop(f"phase2_next_errors_{event_id}", []):
        st.error(issue)
    athletes = get_athletes(db_path, event_id)
    heats = get_running_heats(db_path, event_id)
    run_groups = get_run_groups(db_path, event_id)

    if not heats:
        st.warning("No running heats were found in the Master Dataset.")
        return

    units = _navigation_units(heats, run_groups)
    key = f"phase2_heat_{event_id}"
    if key not in st.session_state or st.session_state[key] not in heats:
        st.session_state[key] = min(heats)

    current_heat = int(st.session_state[key])
    current_unit = _unit_for_heat(current_heat, units)
    idx = _unit_index(current_unit, units)

    control1, control2 = st.columns(2)
    with control1:
        jump = st.selectbox(
            "Jump to Heat",
            heats,
            index=heats.index(current_heat),
            format_func=lambda x: (
                _label(_unit_for_heat(x, units), len(heats))
                if len(_unit_for_heat(x, units)) > 1
                else f"Heat {x}"
            ),
            key=f"jump_heat_{event_id}_{current_heat}",
        )
        if jump != current_heat:
            st.session_state[key] = jump
            st.rerun()

    with control2:
        combine_key = f"phase2_combine_{event_id}_{_selected_key(current_unit)}"
        selected = st.multiselect(
            "Combine Heats",
            heats,
            default=current_unit,
            format_func=lambda x: f"Heat {x}",
            key=combine_key,
        )

    if not selected:
        st.info("Select the heat(s) to map.")
        return

    selected = sorted(set(int(x) for x in selected))
    combined = len(selected) > 1

    if combined:
        st.warning(
            f"Selected heats: {', '.join(map(str, selected))}. "
            "Confirm that these heats were combined for the physical run."
        )
        if not st.checkbox(
            "Yes, these selected heats were combined",
            key=f"confirm_combined_{event_id}_{_selected_key(selected)}",
        ):
            st.info("Confirm the combined heats before entering positions.")
            return

    current = sorted(
        [
            a for a in athletes
            if a.get("running_heat") in selected
            and str(a.get("athlete_number", "")).strip()
            and str(a.get("athlete_name", "")).strip()
        ],
        key=lambda a: a["sort_order"],
    )

    st.markdown(
        f'<div class="phase2-heading">'
        f'<div class="phase2-heat-title">{_label(selected, len(heats))}</div>'
        '<div class="phase2-instruction">Leave position blank for an athlete who did not run.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    editor_key = f"phase2_editor_{event_id}_{_selected_key(selected)}"
    editor_df = pd.DataFrame([
        {
            "Athlete No.": a["athlete_number"],
            "Age Group": a.get("group_name") or "",
            "Athlete Name": a["athlete_name"],
            "Position": "" if a.get("run_position") is None else str(a["run_position"]),
        }
        for a in current
    ])

    left, middle, right = st.columns([1.55, 8.9, 1.55], vertical_alignment="center")
    with left:
        prev_clicked = st.button(
            "← Previous Heat",
            disabled=idx == 0,
            use_container_width=True,
            key=f"prev_heat_{event_id}",
        )
    with middle:
        st.data_editor(
            editor_df,
            hide_index=True,
            use_container_width=True,
            # Size the editor to the actual number of athlete rows. Keeping the
            # height row-derived prevents Streamlit from displaying spare blank rows.
            height=max(100, 35 * max(len(editor_df), 1) + 38),
            num_rows="fixed",
            key=editor_key,
            column_config={
                "Athlete No.": st.column_config.TextColumn("Athlete No.", disabled=True, width="small"),
                "Age Group": st.column_config.TextColumn("Age Group", disabled=True, width="small"),
                "Athlete Name": st.column_config.TextColumn("Athlete Name", disabled=True, width="medium"),
                "Position": st.column_config.TextColumn(
                    "Position",
                    width="small",
                    help="Enter a positive integer. Press Enter to move to the next athlete row. Leave blank if the athlete did not run.",
                ),
            },
        )
    with right:
        next_clicked = st.button(
            "Next Heat →",
            disabled=idx == len(units) - 1,
            use_container_width=True,
            key=f"next_heat_{event_id}",
        )

    target_unit = None
    if prev_clicked and idx > 0:
        target_unit = units[idx - 1]
    elif next_clicked and idx < len(units) - 1:
        target_unit = units[idx + 1]

    if target_unit is not None:
        positions = _read_editor_positions(current, selected, editor_key)
        issues = validate_positions(current, positions)
        if issues:
            for issue in issues:
                st.error(issue)
            return

        # Navigation is the persistence point. The current heat/group is written
        # before moving, so at most the currently edited heat can be lost.
        save_run_positions(db_path, event_id, selected, positions)

        blanks = [
            a["athlete_number"]
            for a in current
            if positions.get(str(a["athlete_number"])) is None
        ]

        if next_clicked and blanks:
            pending_key = f"phase2_pending_{event_id}"
            st.session_state[pending_key] = {
                "target_unit": target_unit,
                "selected": selected,
                "blank_count": len(blanks),
            }
            st.rerun()

        st.session_state.pop(f"phase2_pending_{event_id}", None)
        st.session_state[key] = min(target_unit)
        st.rerun()

    pending = st.session_state.get(f"phase2_pending_{event_id}")
    if pending:
        blank_count = int(pending.get("blank_count", 0))
        target_unit = [int(x) for x in pending.get("target_unit", [])]

        confirm_col1, confirm_col2 = st.columns([3.4, 2.0], vertical_alignment="bottom")
        with confirm_col2:
            with st.container(key="phase2_confirm_action"):
                st.markdown(
                    f'<div class="phase2-confirm-message">⚠ Positions left blank: '
                    f'<strong>{blank_count}</strong></div>',
                    unsafe_allow_html=True,
                )
                confirm_clicked = st.button(
                    "⚠ Confirm and Continue",
                    key=f"confirm_continue_{event_id}",
                    use_container_width=False,
                )

        if confirm_clicked:
            st.session_state.pop(f"phase2_pending_{event_id}", None)
            st.session_state[key] = min(target_unit)
            st.rerun()

    _controls_left, controls_middle, _controls_right = st.columns([1.55, 8.9, 1.55])
    with controls_middle:
        _render_compact_athlete_controls(db_path, event_id, athletes, selected)

    # Phase 2 export: available at any point, based only on mappings already
    # persisted to SQLite.
    st.divider()
    st.subheader("Run Position Export")
    st.caption("Export all run-position mappings persisted so far. The export includes the heat or combined-heat group for each athlete.")

    export_athletes = get_athletes(db_path, event_id)
    export_groups = get_run_groups(db_path, event_id)
    run_position_rows = [
        a for a in export_athletes
        if a.get("run_group_key")
    ]

    if run_position_rows:
        from database.repository import get_event
        event = get_event(db_path, event_id)
        xlsx = build_run_positions_xlsx(export_athletes, export_groups)
        event_name = (event["name"] if event else "Event").strip()
        from exporters.filenames import event_filename
        st.download_button(
            "📥 Export Run Positions",
            data=xlsx,
            file_name=event_filename(event_name,"Run Positions","xlsx",event["start_date"] if event else None),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=False,
            key=f"export_run_positions_{event_id}",
        )
    else:
        st.info("No run positions have been persisted yet. Complete a heat and use Next Heat or Previous Heat to save its positions.")

    st.subheader("Restore Run Position Export")
    imported_file = st.file_uploader(
        "Restore a Run Position Export",
        type=["xlsx"],
        key=f"import_run_positions_{event_id}",
    )
    if imported_file and st.button("Restore Run Positions", key=f"restore_run_positions_{event_id}"):
        try:
            restored = restore_run_position_mappings(
                db_path,
                event_id,
                parse_run_positions_excel(imported_file),
            )
        except Exception as exc:
            st.error(f"Run Position Export could not be restored: {exc}")
        else:
            st.success(f"Restored {restored} run-position mapping(s).")
            st.rerun()
