from __future__ import annotations

import pandas as pd
import streamlit as st

from database.repository import (
    get_athletes,
    get_run_groups,
    get_running_heats,
    save_run_positions,
)
from exporters.run_positions import build_run_positions_xlsx
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


def render(db_path: str, event_id: int):
    st.header("Phase 2 · Run Position Mapping")
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
        safe_name = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in event_name).strip() or "Event"
        st.download_button(
            "📥 Export Run Positions",
            data=xlsx,
            file_name=f"{safe_name} Run Positions.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=False,
            key=f"export_run_positions_{event_id}",
        )
    else:
        st.info("No run positions have been persisted yet. Complete a heat and use Next Heat or Previous Heat to save its positions.")
