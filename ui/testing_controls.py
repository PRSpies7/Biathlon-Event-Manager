"""Deliberate, visually distinct test-event controls."""
import streamlit as st
from services.event_testing import contains_test_data, generate_test_positions, generate_test_results


def test_data_notice(db_path,event_id):
    if contains_test_data(db_path,event_id):
        st.warning("This event contains generated test data. Its outputs are for testing, not official results.")


def render_testing_controls(db_path,event_id,phase):
    test_data_notice(db_path,event_id)
    with st.expander("Testing only — sample event data"):
        st.caption("Fills missing values only. Existing positions and times are kept. Use a separate test event.")
        enabled=st.checkbox("I am using a test event",key=f"test_event_confirm_{phase}_{event_id}")
        with st.container(key=f"test_data_actions_{phase}"):
            label="Generate test finish positions" if phase==2 else "Generate test results"
            if st.button(label,icon=":material/science:",disabled=not enabled,key=f"generate_test_data_{phase}_{event_id}") and enabled:
                try:
                    if phase==2:
                        from ui.phase2_positions import save_current_mapping
                        issues=save_current_mapping(db_path,event_id)
                        if issues:
                            raise ValueError("\n".join(issues))
                        count=generate_test_positions(db_path,event_id)
                        for key in list(st.session_state):
                            if key.startswith(f"phase2_editor_{event_id}_"):
                                del st.session_state[key]
                    else:
                        count=generate_test_results(db_path,event_id)
                    st.session_state[f"test_data_message_{phase}_{event_id}"]=f"Generated {count} test {'positions' if phase==2 else 'times'}; existing values were kept."
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        message=st.session_state.pop(f"test_data_message_{phase}_{event_id}",None)
        if message:
            st.success(message)
