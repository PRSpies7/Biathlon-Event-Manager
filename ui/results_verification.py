"""One review interface shared by Step 4 and standalone verification."""
from dataclasses import asdict
from hashlib import sha256
from uuid import uuid4
import json

import pandas as pd
import streamlit as st

from parsers.manual_results_pdf import extract_manual_pdf
from parsers.verification_results import parse_electronic_results
from services.results_verification import (ManualReading, verify_results, formatted_time, no_start, manual_value,
    apply_event_results, reconcile_results, event_results)


def _signature(electronic, run, swim):
    return sha256(json.dumps([asdict(r) for r in electronic], sort_keys=True).encode()
                  + (run.getvalue() if run else b'') + (swim.getvalue() if swim else b'')).hexdigest()


def render_verification(electronic, scope, db_path=None, event_id=None):
    run = st.file_uploader('Manual Run Results', type=['pdf'], key=f'{scope}_run_pdf')
    swim = st.file_uploader('Manual Swim Results', type=['pdf'], key=f'{scope}_swim_pdf')
    state_key = f'{scope}_review'
    signature = _signature(electronic, run, swim)
    state = st.session_state.get(state_key)
    if state and state['signature'] != signature:
        st.session_state.pop(state_key, None)
        state = None
    if st.button('Verify Results', key=f'{scope}_verify', disabled=not (run and swim and electronic)):
        try:
            run_rows, run_warnings = extract_manual_pdf(run.getvalue(), 'run')
            swim_rows, swim_warnings = extract_manual_pdf(swim.getvalue(), 'swim')
            manual = run_rows + swim_rows
            issues = verify_results(electronic, manual)
        except Exception as exc:
            st.error(f'Could not verify the PDFs: {exc}')
            return
        state = {'signature': signature, 'electronic': electronic, 'manual': manual,
                 'issues': issues, 'warnings': run_warnings + swim_warnings, 'generation': uuid4().hex,
                 'applied': set()}
        st.session_state[state_key] = state
    if not state:
        st.caption('Upload both manual PDFs to compare Run and Swim together. Only issues requiring attention are shown.')
        return
    for warning in state['warnings']:
        st.warning(warning)
    # Preserve recognized identities; add editable placeholders when pages are scans
    # or an expected athlete has no extracted row. No times are invented.
    rows = [asdict(r) for r in state['manual']]
    represented = {(i.target_id, i.discipline) for i in state['issues'] if i.manual_time is not None}
    for issue in state['issues']:
        if issue.status == 'MISSING_MANUAL_RESULT' and (issue.athlete_id, issue.discipline) not in represented:
            if not any(r['athlete_id'] == issue.athlete_id and r['discipline'] == issue.discipline for r in rows):
                rows.append(asdict(ManualReading(issue.athlete_id, issue.athlete_name, issue.discipline, None)))
    columns = ['athlete_id', 'athlete_name', 'discipline', 'time', 'source']
    original = [{k: r[k] or '' for k in columns} for r in rows]
    with st.expander('Review or transcribe manual readings'):
        st.caption('Check the original PDFs. Correct unreadable times or athlete IDs here, then recheck. No age group or gender is used for matching.')
        edited = st.data_editor(pd.DataFrame(original, columns=columns), hide_index=True, num_rows='dynamic',
            key=f"{scope}_readings_{state['generation']}",
            column_config={'discipline': st.column_config.SelectboxColumn('Result type', options=['run', 'swim'], required=True),
                           'athlete_id': 'Athlete ID', 'athlete_name': 'Athlete name', 'time': 'Manual time', 'source': 'Source'})
        records = edited.fillna('').to_dict('records')
        changed = records != original
        if st.button('Recheck edited readings', key=f'{scope}_recheck'):
            manual = []
            for index, row in enumerate(records):
                certain = index >= len(rows) or row != original[index] or rows[index]['certain']
                manual.append(ManualReading(str(row['athlete_id']), str(row['athlete_name']),
                                            row['discipline'], str(row['time']) or None, certain, str(row['source'])))
            try:
                state['issues'] = verify_results(electronic, manual)
            except ValueError as exc:
                st.error(str(exc))
            else:
                state.update(manual=manual, generation=uuid4().hex, applied=set())
                st.rerun()
    if changed:
        st.info('Recheck edited readings before applying decisions.')
    issues = state['issues']
    if not issues:
        st.success('No verification issues. All expected manual readings are present and within 0.40 seconds.')
        return
    unresolved = [i for i in issues if i.key not in state['applied']]
    st.caption(f'{len(unresolved)} issue(s) remaining. Differences above 1.00 second appear first.')
    choices = {}
    for issue in unresolved:
        with st.container(border=True):
            high_risk = issue.difference is not None and issue.difference > 1
            title = f'{issue.athlete_id or "Unknown ID"} · {issue.athlete_name or "Unknown athlete"} · {issue.discipline.title()}'
            (st.warning if high_risk else st.write)(('⚠ High risk — ' if high_risk else '') + title)
            difference = f'{issue.difference:.3f} s' if issue.difference is not None else '—'
            st.write(f'Manual: {issue.manual_time or "—"} · Electronic: {issue.electronic_time or "—"} · Difference: {difference}')
            if manual_value(issue.manual_time)[1]:
                st.caption(f'Proposed shorthand reading: {formatted_time(issue.manual_time) or "invalid"}. Confirm against the PDF before choosing Use Manual.')
            if no_start(issue.manual_time):
                st.caption('N/S means did not start. Use Manual clears this discipline’s captured time.')
            st.caption(f'{issue.status} · {issue.matching}' + (f' · {issue.source}' if issue.source else ''))
            if not issue.target_id:
                st.info('Correct the athlete identification or duplicate reading above, then recheck. No result will be changed.')
                continue
            options = ['Use Electronic']
            if formatted_time(issue.manual_time) or no_start(issue.manual_time):
                options.append('Use Manual')
            choice = st.radio('Choose result', options, index=None, horizontal=True,
                              key=f"{scope}_decision_{state['generation']}_{issue.key}")
            if choice:
                choices[issue.key] = choice
    if st.button('Apply Selected Results', key=f'{scope}_apply', disabled=changed or not choices):
        try:
            if db_path is not None:
                apply_event_results(db_path, event_id, state['electronic'], issues, choices)
                from database.repository import get_athletes
                state['electronic'] = event_results(get_athletes(db_path, event_id))
                state['signature'] = _signature(state['electronic'], run, swim)
                state['applied'].update(choices)
                for key in list(st.session_state):
                    if key.startswith(f'phase4_editor_{event_id}_'):
                        st.session_state.pop(key, None)
                st.session_state[f'{scope}_notice'] = 'Selected results applied. Final results and exports refreshed.'
            else:
                state['reconciled'] = reconcile_results(state.get('reconciled', electronic), issues, choices)
                state['applied'].update(choices)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if state.get('reconciled') is not None:
        st.caption('Reconciled results for this verification session only. No season database changes.')
        st.dataframe([asdict(r) for r in state['reconciled']], hide_index=True)


def render():
    st.header('Results Verification')
    st.subheader('Results to Verify')
    upload = st.file_uploader('Electronic final results', type=['xml', 'xlsx', 'pdf'], key='verification_electronic')
    if not upload:
        st.info('Upload final-results XML or a supported published season-results Excel/PDF file.')
        return
    try:
        electronic = parse_electronic_results(upload.getvalue(), upload.name)
    except Exception as exc:
        st.error(f'Could not read final results: {exc}')
        return
    render_verification(electronic, 'verification_standalone')
