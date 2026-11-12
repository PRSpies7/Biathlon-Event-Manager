"""Exercise the real Streamlit navigation and preview decisions with temporary data."""
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from database.season_repository import season_snapshot
from test_season_results import sample_event


ROOT = Path(__file__).resolve().parents[1]


def app_test(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SEASON_DATABASE_PATH", raising=False)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "TimeDrops JSON example.json").write_text("{}", encoding="utf-8")
    (tmp_path / "style.css").write_text("", encoding="utf-8")
    source = (ROOT / "app.py").read_text(encoding="utf-8").replace(
        "BASE_DIR = Path(__file__).resolve().parent", f"BASE_DIR = Path({str(tmp_path)!r})")
    return AppTest.from_string(source, default_timeout=15).run()


def test_navigation_independent_of_workflow_and_reference(tmp_path, monkeypatch):
    app = app_test(tmp_path, monkeypatch)
    assert not app.exception
    app.radio(key="app_module").set_value("Season Results Database").run()
    assert not app.exception
    assert app.title[0].value == "Season Results Database"
    assert not any(b.key == "btn_next_bottom" for b in app.button)
    # The season module is usable even if the workflow's TimeDrops reference is missing.
    (tmp_path / "data" / "TimeDrops JSON example.json").unlink()
    for view in ("Athletes", "Events"):
        app.session_state["season_view"] = view
        with patch("database.db.init_db", side_effect=AssertionError("Season module must not initialize the workflow database")):
            app.run()
        assert not app.exception and not app.error
        assert app.session_state["season_view"] == view
    assert not any(b.key in {"season_continue","season_back"} for b in app.button)
    (tmp_path / "data" / "TimeDrops JSON example.json").write_text("{}", encoding="utf-8")
    app.radio(key="app_module").set_value("Event Management").run()
    assert not app.exception
    assert any(b.key == "btn_next_bottom" for b in app.button)
    assert app.session_state.current_phase == 1


def test_import_screen_shows_saved_season_results_without_upload(tmp_path, monkeypatch):
    from dataclasses import replace
    from database.season_repository import store_event
    from database.season_db import init_season_db
    app = app_test(tmp_path, monkeypatch)
    db = tmp_path / "data" / "season_results.sqlite"
    init_season_db(db)
    for year in (2026,2027):
        store_event(db,replace(sample_event(),season_year=year))
    app.radio(key="app_module").set_value("Season Results Database").run()
    assert not app.exception and not app.error
    assert app.session_state["season_view"] == "Events"
    assert app.selectbox(key="season_selected_year").value == 2027
    assert any("Event name" in frame.value.columns for frame in app.dataframe)
    app.selectbox(key="season_selected_year").set_value(2026).run()
    events = next(frame.value for frame in app.dataframe if "Event name" in frame.value.columns)
    assert set(events["Season"]) == {2026}
    app.button(key="season_open_reports").click().run()
    assert not app.exception and not app.error
    assert app.selectbox(key="season_selected_year").value == 2026
    assert not any(b.key in {"season_back","season_continue"} for b in app.button)
    app.button(key="reports_open_imports").click().run()
    assert not app.exception and not app.error
    assert app.selectbox(key="season_selected_year").value == 2026
    assert app.session_state["season_view"] == "Events"
    assert next(e for e in app.expander if e.label == "Import or update events").proto.expanded


def test_reports_latest_event_uses_competition_date_not_import_order(tmp_path,monkeypatch):
    from dataclasses import replace
    from datetime import date
    from database.season_db import init_season_db
    from database.season_repository import store_event
    app = app_test(tmp_path,monkeypatch)
    db = tmp_path/"data/season_results.sqlite"
    init_season_db(db)
    base = sample_event()
    store_event(db,replace(base,name="League 5",event_date=date(2026,11,10),season_year=2027))
    store_event(db,replace(base,name="Earlier event imported later",event_date=date(2026,10,3),season_year=2027))
    with patch("ui.season_results.render_reports"):
        app.radio(key="app_module").set_value("Reports").run()
    assert not app.exception and not app.error
    assert any(i.value == "Latest event in this season: League 5 · Event date: 2026-11-10" for i in app.info)
    assert not any("Earlier event imported later" in i.value or "Imported:" in i.value for i in app.info)


def test_preview_import_duplicate_skip_overwrite_affiliation(tmp_path, monkeypatch):
    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    event = sample_event()
    app.session_state.season_pending = [{"event": event, "token": "first", "outcome": ""}]
    app.run()
    assert not app.exception
    app.button(key="season_import").click().run()
    db = tmp_path / "data" / "season_results.sqlite"
    assert len(season_snapshot(db)["results"]) == 2
    # Re-import never writes without an explicit duplicate choice.
    app.session_state.season_pending = [{"event": event, "token": "second", "outcome": ""}]
    app.run()
    assert app.radio(key="season_action_second").value == "Skip"
    assert "This event already exists." in app.warning[0].value
    event.results = event.results[:1]
    app.radio(key="season_action_second").set_value("Overwrite").run()
    app.button(key="season_import").click().run()
    assert not app.exception
    assert len(season_snapshot(db)["results"]) == 1
    app.session_state["season_view"] = "Athletes"
    app.run()
    assert not app.exception
    app.checkbox[0].uncheck()
    next(b for b in app.button if b.label == "Save affiliation").click().run()
    assert not app.exception
    assert season_snapshot(db)["athletes"][0]["affiliated"] == 0
    app.radio(key="app_module").set_value("Reports").run()
    assert not app.exception


def test_duplicate_files_in_same_batch_require_a_choice(tmp_path, monkeypatch):
    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    app.session_state.season_pending = [
        {"event": sample_event(), "token": "one", "outcome": ""},
        {"event": sample_event(), "token": "two", "outcome": ""},
    ]
    app.run()
    assert app.radio(key="season_action_two").value == "Skip"
    app.button(key="season_import").click().run()
    assert not app.exception
    assert len(season_snapshot(tmp_path / "data" / "season_results.sqlite")["events"]) == 1


def test_season_start_and_confirmed_database_reset(tmp_path, monkeypatch):
    from dataclasses import replace
    from datetime import date
    from database.season_repository import store_event

    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    db = tmp_path / "data" / "season_results.sqlite"
    event = sample_event()
    store_event(db, event)
    store_event(db, replace(event, name="Earlier event", event_date=date(2026, 7, 1)))
    app.session_state["season_view"] = "Events"
    app.run()
    assert app.selectbox(key="season_selected_year").value is None
    assert any("no confirmed season" in w.value for w in app.warning)
    app.session_state["season_view"] = "Athletes"
    app.run()
    before = season_snapshot(db)
    app.button(key="season_reset").click().run()
    assert season_snapshot(db) == before
    assert any("permanently deletes" in e.value for e in app.error)
    app.button(key="season_cancel_reset").click().run()
    assert season_snapshot(db) == before
    assert not any(b.key == "season_confirm_reset_button" for b in app.button)
    app.session_state.season_pending = [{"event": event, "token": "stale", "outcome": "Imported"}]
    app.button(key="season_reset").click().run()
    app.button(key="season_confirm_reset_button").click().run()
    assert not app.exception
    assert all(not rows for rows in season_snapshot(db).values())
    assert "season_pending" not in app.session_state
    assert app.button(key="season_reset").disabled
    assert any("has been reset" in s.value for s in app.success)
    app.session_state["season_view"] = "Events"
    app.run()
    assert not any("Current season starting" in c.value for c in app.caption)


def test_reports_and_current_record_save(tmp_path, monkeypatch):
    from database.season_repository import store_event
    from parsers.season_records import validate_record_benchmarks

    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    db = tmp_path / "data" / "season_results.sqlite"
    store_event(db, sample_event())
    app.radio(key="app_module").set_value("Reports").run()
    assert not app.exception
    assert {"Season qualification and results","Athlete qualification","School qualification and teams","Ranked athletes","Affiliation and follow-up","Records"} <= {s.value for s in app.subheader}
    app.session_state.season_records_preview = {"source": "records.xlsx", "records": validate_record_benchmarks([
        {"category": "U/11 GIRLS", "athlete_number": "00999", "total_points": "2000"}])}
    app.run()
    app.button(key="season_records_save").click().run()
    assert not app.exception
    assert len(season_snapshot(db)["records"]) == 1
    assert any("Current records saved" in s.value for s in app.success)
    assert any("Record comparison" in d.value.columns and "Exceeded" in d.value["Record comparison"].values
               for d in app.dataframe)
    # All seven reports plus the input template are available after records are saved.
    assert len(app.get("download_button")) == 8


def test_reports_receive_only_selected_season(tmp_path, monkeypatch):
    from dataclasses import replace
    from database.season_repository import store_event

    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    db = tmp_path / "data" / "season_results.sqlite"
    for year in (2026, 2027):
        store_event(db, replace(sample_event(), season_year=year))
    with patch("ui.season_results.render_reports") as reports:
        app.radio(key="app_module").set_value("Reports").run()
        assert not app.exception
        assert {e["season_year"] for e in reports.call_args.args[1]["events"]} == {2027}
        app.selectbox(key="season_selected_year").set_value(2026).run()
        assert not app.exception
        assert {r["season_year"] for r in reports.call_args.args[1]["results"]} == {2026}


def test_reset_and_reimport_selects_imported_season(tmp_path, monkeypatch):
    from dataclasses import replace
    from database.season_repository import store_event

    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    db = tmp_path / "data" / "season_results.sqlite"
    event = replace(sample_event(), season_year=2027)
    store_event(db, event)
    app.session_state["season_view"] = "Athletes"
    app.run()
    app.button(key="season_reset").click().run()
    app.button(key="season_confirm_reset_button").click().run()
    # Viewing the empty database leaves the season selector on legacy/unassigned.
    app.session_state["season_view"] = "Events"
    app.run()
    assert app.selectbox(key="season_selected_year").value is None
    app.session_state["season_view"] = "Events"
    app.run()
    app.session_state.season_pending = [{"event": event, "token": "again", "outcome": ""}]
    app.run()
    app.button(key="season_import").click().run()
    assert not app.exception
    assert len(season_snapshot(db, 2027)["results"]) == 2
    app.button(key="season_saved_2027").click().run()
    assert app.selectbox(key="season_selected_year").value == 2027
    assert len(app.dataframe[0].value) == 1


def test_all_duplicate_skips_disable_import(tmp_path, monkeypatch):
    from dataclasses import replace
    from database.season_repository import store_event

    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    event = replace(sample_event(), season_year=2027)
    db = tmp_path / "data" / "season_results.sqlite"
    store_event(db, event)
    app.session_state.season_pending = [{"event": event, "token": "duplicate", "outcome": ""}]
    app.run()
    assert app.button(key="season_import").disabled
    assert any("Nothing is selected" in message.value for message in app.info)
    app.radio(key="season_action_duplicate").set_value("Overwrite").run()
    assert not app.button(key="season_import").disabled


def test_workflow_radios_and_steppers_stay_in_sync(tmp_path, monkeypatch):
    from database.repository import create_event

    app = app_test(tmp_path, monkeypatch)
    event_steps = ['1. Event Setup', '2. Run Position Mapping', '3. Results Ingestion', '4. Final Results & Export']
    season_steps = ['1. Import Results', '2. Imported Events', '3. Athlete Database']

    def check_stepper(labels, active):
        steps = [m.value for m in app.markdown if 'class="step-item ' in m.value]
        assert len(steps) == len(labels)
        assert all(label in step for label, step in zip(labels, steps))
        assert [i for i, step in enumerate(steps) if 'step-item active' in step] == [active]
        assert not app.exception

    assert app.radio(key='workflow_phase').label == 'Workflow Steps'
    assert app.radio(key='workflow_phase').options == event_steps
    check_stepper(event_steps, 0)
    # An unopened event still cannot navigate past setup.
    app.radio(key='workflow_phase').set_value(3).run()
    assert app.radio(key='workflow_phase').value == 1
    check_stepper(event_steps, 0)
    db = tmp_path / 'data/biathlon_events.sqlite'
    eid = create_event(db, 'Navigation', 'GN', '2026-09-01', 'SCM', 6)
    app.session_state.event_id = eid
    app.run()
    app.radio(key='workflow_phase').set_value(3).run()
    check_stepper(event_steps, 2)
    app.button(key='btn_next_bottom').click().run()
    assert app.radio(key='workflow_phase').value == 4
    check_stepper(event_steps, 3)
    app.button(key='btn_prev_bottom').click().run()
    assert app.radio(key='workflow_phase').value == 3
    app.radio(key='app_module').set_value('Season Results Database').run()
    assert app.session_state["season_view"] == "Events"
    assert not [m for m in app.markdown if 'class="step-item ' in m.value]
    app.session_state["season_view"] = "Athletes"
    app.run()
    app.button(key='season_open_reports').click().run()
    assert app.radio(key='app_module').value == 'Reports'
    app.button(key='reports_open_imports').click().run()
    assert app.session_state["season_view"] == "Events"
    assert next(e for e in app.expander if e.label == "Import or update events").proto.expanded
    app.radio(key='app_module').set_value('Event Management').run()
    assert app.radio(key='workflow_phase').value == 3
    check_stepper(event_steps, 2)
    app.button(key='start_new_session').click().run()
    assert app.radio(key='workflow_phase').value == 1
    check_stepper(event_steps, 0)
