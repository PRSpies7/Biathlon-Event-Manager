from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from database.db import init_db
from database.repository import get_event, get_events
from ui.phase1_setup import render as render_phase1
from ui.phase2_positions import render as render_phase2
from ui.phase3_processing import render as render_phase3
from ui.phase4_export import render as render_phase4

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "biathlon_events.sqlite"
TIMEDROPS_REF = DATA_DIR / "TimeDrops JSON example.json"
VERSION = "v1.15.1"
TOTAL_PHASES = 4

st.set_page_config(
    page_title=f"Biathlon Event Manager {VERSION}",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db(DB_PATH)

# ============================================================================
# VISUAL THEME
# ============================================================================
STYLE_PATH = BASE_DIR / "style.css"
try:
    st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
except OSError as exc:
    st.error(f"Application styling could not be loaded: {exc}")

# ============================================================================
# SESSION STATE / NAVIGATION
# ============================================================================
if "event_id" not in st.session_state:
    st.session_state.event_id = None
if "current_phase" not in st.session_state:
    # current_phase is the V1.3 navigation controller. V1.2 used active_phase.
    st.session_state.current_phase = st.session_state.get("active_phase", 1)
if "new_session_token" not in st.session_state:
    st.session_state.new_session_token = 0

# Keep the old V1.2 key synchronized for compatibility with any external code
# that may have relied on it, while current_phase remains the navigation source.
st.session_state.active_phase = st.session_state.current_phase

phases = {
    1: "1. Event Setup",
    2: "2. Run Position Mapping",
    3: "3. Results Ingestion",
    4: "4. Final Results & Export",
}


def go_next_phase():
    """Move forward one phase without changing persistent event data."""
    if st.session_state.current_phase < TOTAL_PHASES:
        if st.session_state.current_phase > 1 and not st.session_state.event_id:
            return
        st.session_state.current_phase += 1
        st.session_state.active_phase = st.session_state.current_phase


def go_prev_phase():
    """Move backward one phase without changing persistent event data."""
    if st.session_state.current_phase > 1:
        st.session_state.current_phase -= 1
        st.session_state.active_phase = st.session_state.current_phase


def set_phase(phase_number: int):
    """Direct phase navigation; no SQLite data is modified."""
    phase_number = max(1, min(TOTAL_PHASES, int(phase_number)))
    if phase_number > 1 and not st.session_state.event_id:
        st.session_state.current_phase = 1
    else:
        st.session_state.current_phase = phase_number
    st.session_state.active_phase = st.session_state.current_phase


def reset_transient_state():
    """Clear temporary upload/editor state only. SQLite data is untouched."""
    keys = [
        k for k in list(st.session_state.keys())
        if any(
            token in k
            for token in (
                "run_parse_",
                "swim_parse_",
                "pending_process_",
                "last_process_",
                "last_run_process_",
                "last_swim_process_",
                "phase4_editor_",
                "confirm_reset_phase4_",
            )
        )
    ]
    for key in keys:
        st.session_state.pop(key, None)
    st.session_state.pop("timedrops_json", None)


def start_new_session():
    """Start a fresh event workflow while preserving all saved SQLite sessions."""
    st.session_state.event_id = None
    st.session_state.pop("session_selector", None)
    st.session_state.current_phase = 1
    st.session_state.active_phase = 1
    reset_transient_state()
    # A new uploader key guarantees Phase 1 presents a genuinely fresh upload control.
    st.session_state.new_session_token += 1


def open_event(event_id: int):
    st.session_state.event_id = event_id
    st.session_state.current_phase = 1
    st.session_state.active_phase = 1
    reset_transient_state()
    st.rerun()

# ============================================================================
# SIDEBAR
# ============================================================================
with st.sidebar:
    st.markdown(
        f'<div class="sidebar-brand"><div class="sidebar-brand-title">Biathlon Event Manager</div>'
        f'<div class="sidebar-brand-version">{VERSION}</div></div>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.subheader("Workflow Steps")
    for phase_number, label in phases.items():
        is_current = st.session_state.current_phase == phase_number
        st.button(
            label,
            key=f"side_nav_{phase_number}",
            on_click=set_phase,
            args=(phase_number,),
            type="primary" if is_current else "secondary",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Sessions")
    events = get_events(str(DB_PATH))

    def _handle_session_change(event_options: dict[str, int]):
        selected_label = st.session_state.get("session_selector")
        if selected_label in event_options:
            open_event(event_options[selected_label])

    if events:
        options = {
            f"{e['name']} · {e['start_date']} · ID {e['id']}": e["id"]
            for e in events
        }
        labels = list(options)
        default_idx = next(
            (i for i, label in enumerate(labels) if options[label] == st.session_state.event_id),
            0,
        )
        st.selectbox(
            "Available Sessions",
            labels,
            index=default_idx,
            key="session_selector",
            on_change=_handle_session_change,
            args=(options,),
        )
    else:
        st.caption("No saved sessions yet.")

    if st.button("＋ Start New Session", use_container_width=True, key="start_new_session"):
        start_new_session()
        st.rerun()

    if st.session_state.event_id:
        ev = get_event(str(DB_PATH), st.session_state.event_id)
        if ev:
            st.divider()
            st.caption(f"Session ID: {ev['id']}")

    st.divider()
    st.caption(
        f"{VERSION} supports Run Excel + Swim TXT. "
        "Run TXT timing-button import is reserved for a future enhancement."
    )

# ============================================================================
# WORKFLOW STEPPER
# ============================================================================
# The large application header was intentionally removed in V1.10, but the
# workflow stepper remains the primary at-a-glance navigation indicator.
st.markdown('<div class="workflow-stepper">', unsafe_allow_html=True)
step_cols = st.columns(TOTAL_PHASES)
for idx, (phase_number, phase_label) in enumerate(phases.items()):
    with step_cols[idx]:
        active_class = "active" if st.session_state.current_phase == phase_number else ""
        st.markdown(
            f'<div class="step-item {active_class}">{phase_label}</div>',
            unsafe_allow_html=True,
        )
st.markdown('</div>', unsafe_allow_html=True)

# ============================================================================
# TIME DROPS REFERENCE
# ============================================================================
try:
    reference_json = json.loads(TIMEDROPS_REF.read_text(encoding="utf-8"))
except Exception as exc:
    st.error(f"TimeDrops reference JSON could not be loaded: {exc}")
    st.stop()

# ============================================================================
# PHASE RENDERING
# ============================================================================
curr = st.session_state.current_phase

try:
    if curr == 1:
        render_phase1(str(DB_PATH), reference_json)
    elif not st.session_state.event_id:
        st.warning("Initialize or open an event in Phase 1 before using this phase.")
    elif curr == 2:
        render_phase2(str(DB_PATH), st.session_state.event_id)
    elif curr == 3:
        render_phase3(str(DB_PATH), st.session_state.event_id)
    elif curr == 4:
        render_phase4(str(DB_PATH), st.session_state.event_id)
except Exception as exc:
    st.error(f"Error loading Phase {curr}: {exc}")


# ============================================================================
# FIXED BOTTOM PHASE NAVIGATION
# ============================================================================
# This navigation is deliberately independent of the large application header.
# It was present in the working V1.9 workflow and must remain available on all
# phases after the header was removed.
st.markdown('<div class="bottom-phase-navigation">', unsafe_allow_html=True)
nav_left, nav_mid, nav_right = st.columns([1.5, 2.0, 1.5], vertical_alignment="center")

with nav_left:
    previous_disabled = st.session_state.current_phase <= 1
    if st.button(
        "← Previous Phase",
        key="btn_prev_bottom",
        disabled=previous_disabled,
        use_container_width=True,
        on_click=go_prev_phase,
    ):
        pass

with nav_mid:
    st.markdown(
        f'<div class="bottom-phase-step">Step {st.session_state.current_phase} of {TOTAL_PHASES}</div>',
        unsafe_allow_html=True,
    )

with nav_right:
    next_disabled = (
        st.session_state.current_phase >= TOTAL_PHASES
        or (st.session_state.current_phase >= 1 and not st.session_state.event_id)
    )
    if st.button(
        "Next Phase →",
        key="btn_next_bottom",
        disabled=next_disabled,
        type="primary",
        use_container_width=True,
        on_click=go_next_phase,
    ):
        pass
st.markdown('</div>', unsafe_allow_html=True)
