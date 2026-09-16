from dataclasses import replace
from io import BytesIO
from unittest.mock import patch
from decimal import Decimal

import pytest

from services.results_verification import (VerificationResult as Result, ManualReading as Reading,
    verify_results, seconds, formatted_time, reconcile_results, event_results, apply_event_results)
from parsers.verification_results import parse_electronic_results
from parsers.manual_results_pdf import extract_manual_pdf


def electronic():
    return [Result('001', 'John Smith', '01:00.00', '00:31.82', True, False)]


def reading(time='01:01.00', **kwargs):
    return Reading(kwargs.get('athlete_id', '001'), kwargs.get('name', 'Wrong printed name'),
                   kwargs.get('discipline', 'run'), time, kwargs.get('certain', True))


@pytest.mark.parametrize('manual,status', [('01:00.40', None), ('01:00.41', 'TIME_DIFFERENCE'),
                                         ('01:01.00', 'TIME_DIFFERENCE'), ('01:01.001', 'HIGH_RISK')])
def test_exact_tolerance(manual, status):
    issues = verify_results(electronic(), [reading(manual)])
    assert [i.status for i in issues] == ([status] if status else [])


def test_identity_hierarchy_and_ambiguity():
    assert verify_results(electronic(), [reading()])[0].matching == 'MATCHED_BY_ID'
    for identity in ('', '999'):
        issue = verify_results(electronic(), [reading(athlete_id=identity, name=' john   SMITH ')])[0]
        assert issue.target_id == '001' and issue.matching == 'MATCHED_BY_NAME'
    duplicate = electronic() + [replace(electronic()[0], athlete_id='002')]
    issue = next(i for i in verify_results(duplicate, [reading(athlete_id='', name='John Smith')]) if i.status == 'AMBIGUOUS_MATCH')
    assert issue.target_id is None
    assert any(i.status == 'NO_MATCH' for i in verify_results(electronic(), [reading(athlete_id='999')]))


def test_run_and_swim_sorted_and_decisions():
    source = [replace(electronic()[0], swim_expected=True)]
    issues = verify_results(source, [reading('01:00.41'), reading('35.00', discipline='swim')])
    assert [i.status for i in issues] == ['HIGH_RISK', 'TIME_DIFFERENCE']
    assert reconcile_results(source, issues, {}) == source
    assert reconcile_results(source, issues, {i.key: 'Use Electronic' for i in issues}) == source
    result = reconcile_results(source, issues, {issues[0].key: 'Use Manual'})
    assert result[0].swim_time == '00:35.00' and result[0].run_time == '01:00.00'


@pytest.mark.parametrize('value,expected', [('31.82', Decimal('31.82')), ('2:34.7', Decimal('154.7'))])
def test_time_normalization(value, expected):
    assert seconds(value) == expected


@pytest.mark.parametrize('value,status', [(None, 'MISSING_MANUAL_RESULT'), ('bad', 'UNREADABLE_MANUAL_TIME'),
                                         ('N/S', 'NO_START_CONFLICT'), ('', 'MISSING_MANUAL_RESULT')])
def test_manual_non_times(value, status):
    issue = verify_results(electronic(), [reading(value)])[0]
    assert issue.status == status
    if value == 'N/S':
        assert reconcile_results(electronic(), [issue], {issue.key: 'Use Manual'})[0].run_time is None


def test_shorthand_and_uncertain_recognition_never_auto_pass():
    source = [replace(electronic()[0], run_time='01:06.44')]
    issue = verify_results(source, [reading('106.44')])[0]
    assert issue.status == 'NONSTANDARD_TIME' and issue.difference == 0
    assert formatted_time(issue.manual_time) == '01:06.44'
    assert verify_results(electronic(), [reading('01:00.00', certain=False)])[0].status == 'UNCERTAIN_RECOGNITION'
    assert verify_results(electronic(), [])[0].status == 'MISSING_MANUAL_RESULT'
    assert verify_results([replace(electronic()[0], run_time=None)], [reading()])[0].status == 'MISSING_ELECTRONIC_RESULT'


def test_duplicate_manual_readings_not_applied():
    issues = verify_results(electronic(), [reading(), reading()])
    assert all(i.status == 'DUPLICATE_MANUAL_RESULT' and i.target_id is None for i in issues)
    with pytest.raises(ValueError):
        reconcile_results(electronic(), issues, {issues[0].key: 'Use Manual'})


@pytest.mark.parametrize('name,surname,expected', [('John Smith', 'John Smith', 'John Smith'),
                                                  ('John', 'Smith', 'John Smith'), ('John Smith', 'Smith', 'John Smith')])
def test_xml_adapter_names(name, surname, expected):
    payload = f'<results><result><athleteNo>001</athleteNo><athleteName>{name}</athleteName><athleteSurname>{surname}</athleteSurname><runtime>2:34.7</runtime></result></results>'.encode()
    result = parse_electronic_results(payload, 'results.xml')[0]
    assert result.athlete_id == '001' and result.athlete_name == expected


def test_existing_published_parser_and_master_excel_adapter():
    from test_season_results import excel_fixture
    from exporters.master_excel import build_master_import_xlsx
    result = parse_electronic_results(excel_fixture().getvalue(), 'league.xlsx')
    assert result[0].athlete_id == '00101' and result[0].run_time == '01:20.10'
    payload = build_master_import_xlsx([{'athlete_number': '001', 'athlete_name': 'John Smith', 'run_time': '01:00.00'}])
    assert parse_electronic_results(payload.getvalue(), 'master.xlsx')[0].athlete_id == '001'


def test_known_run_pdf_geometry_and_recognizer_interface():
    from exporters.heats import build_heats_pdf
    from test_heat_workflow import entries, settings
    from services.heats import generate_heats
    event = dict(settings(), name='Test', host_team='GN', start_date='2026-09-01', season_year=2027, heat_revision=1, course='SCM')
    pdf = build_heats_pdf(generate_heats(entries(2), event), event).getvalue()
    rows, warnings = extract_manual_pdf(pdf, 'run')
    assert len(rows) == 2 and {r.athlete_id for r in rows} == {'100', '101'}
    assert all(r.time is None for r in rows) and warnings
    rows, _ = extract_manual_pdf(pdf, 'run', lambda crop: ('106.44', False))
    assert len(rows) == 2 and all(r.time == '106.44' and not r.certain for r in rows)


def test_known_swim_table_geometry():
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
    payload = BytesIO()
    table = Table([['Lane', '#', 'Athlete Name', 'Age group', 'Heat', 'Time'],
                   ['1', '001', 'John Smith', 'U/13 Boys', '1', 'N/S']])
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
    SimpleDocTemplate(payload).build([table])
    readings, _ = extract_manual_pdf(payload.getvalue(), 'swim')
    assert len(readings) == 1
    assert readings[0].athlete_id == '001' and readings[0].time == 'N/S'
    assert not readings[0].certain


def test_scan_without_text_is_not_a_pass():
    from reportlab.pdfgen.canvas import Canvas
    payload = BytesIO()
    pdf = Canvas(payload)
    pdf.rect(10, 10, 50, 50)
    pdf.showPage()
    pdf.save()
    rows, warnings = extract_manual_pdf(payload.getvalue(), 'run')
    assert rows == [] and any('no readable athlete' in w for w in warnings)
    assert verify_results(electronic(), rows)


def test_existing_update_path_and_stale_guard(tmp_path):
    from database.db import init_db
    from database.repository import create_event, replace_athletes, get_athletes, update_manual_time
    from test_heat_workflow import entries
    db = tmp_path / 'events.sqlite'
    init_db(db)
    eid = create_event(db, 'Test', 'GN', '2026-09-01', 'SCM', 6)
    replace_athletes(db, eid, entries(1))
    update_manual_time(db, eid, '100', 'run_time', '01:00.00')
    source = event_results(get_athletes(db, eid))
    issues = verify_results(source, [Reading('100', '', 'run', '01:02.00', True)])
    run = next(i for i in issues if i.discipline == 'run')
    with patch('database.repository.update_manual_time', wraps=update_manual_time) as update:
        assert apply_event_results(db, eid, source, issues, {}) == 0
        assert apply_event_results(db, eid, source, issues, {run.key: 'Use Electronic'}) == 0
        assert update.call_count == 0
        assert apply_event_results(db, eid, source, issues, {run.key: 'Use Manual'}) == 1
        update.assert_called_once_with(db, eid, '100', 'run_time', '01:02.00')
    row = get_athletes(db, eid)[0]
    assert row['run_time'] == '01:02.00' and row['run_time_manual'] == 1
    with pytest.raises(ValueError, match='changed since verification'):
        apply_event_results(db, eid, source, issues, {run.key: 'Use Manual'})


@pytest.mark.parametrize('standalone', [False, True])
def test_both_screens_use_shared_engine_and_apply(tmp_path, monkeypatch, standalone):
    from test_heat_workflow_ui import opened
    from test_heat_workflow import entries, settings
    from services.heats import generate_heats
    from database.repository import approve_heats, get_event, update_manual_time, get_athletes
    from exporters.results_xml import build_results_xml
    app, db, eid, _ = opened(tmp_path, monkeypatch, generate_heats(entries(1), settings()))
    approve_heats(db, eid, get_event(db, eid)['heat_revision'])
    update_manual_time(db, eid, '100', 'run_time', '01:00.00')
    update_manual_time(db, eid, '100', 'swim_time', '00:31.82')
    electronic_file = BytesIO(build_results_xml(get_athletes(db, eid)))
    electronic_file.name = 'results.xml'
    pdf = BytesIO(b'pdf')
    pdf.name = 'manual.pdf'
    scope = 'verification_standalone' if standalone else f'phase4_verification_{eid}'
    def upload(label, **kwargs):
        return electronic_file if label == 'Electronic final results' else pdf
    def extract(payload, discipline):
        return [Reading('100', 'Athlete 0', discipline, '01:02.00' if discipline == 'run' else '00:32.23', True)], []
    with patch('streamlit.file_uploader', side_effect=upload), patch('ui.results_verification.extract_manual_pdf', side_effect=extract), patch('ui.results_verification.verify_results', wraps=verify_results) as engine:
        if standalone:
            app.radio(key='app_module').set_value('Results Verification').run()
        else:
            app.radio(key='workflow_phase').set_value(4).run()
        assert not app.exception
        app.button(key=f'{scope}_verify').click().run()
        assert not app.exception
        engine.assert_called_once()
        assert len(engine.call_args.args[1]) == 2
        decisions = [r for r in app.radio if '_decision_' in r.key]
        assert len(decisions) == 2 and all(r.value is None for r in decisions)
        decisions[0].set_value('Use Manual').run()
        app.button(key=f'{scope}_apply').click().run()
        assert not app.exception
        if standalone:
            assert get_athletes(db, eid)[0]['run_time'] == '01:00.00'
            assert app.session_state[f'{scope}_review']['reconciled'][0].run_time == '01:02.00'
        else:
            assert get_athletes(db, eid)[0]['run_time'] == '01:02.00'
            from services.event_workspace import workspace_path
            exported = (workspace_path(db, eid) / 'outputs/Review Master Results 2026-09-01.xml').read_text()
            assert '<runtime>01:02.00</runtime>' in exported
        assert len([r for r in app.radio if '_decision_' in r.key]) == 1
