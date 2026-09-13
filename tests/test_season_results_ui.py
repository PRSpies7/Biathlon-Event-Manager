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
    assert app.header[0].value == "Season Results Database"
    assert not any(b.key == "btn_next_bottom" for b in app.button)
    # The season module is usable even if the workflow's TimeDrops reference is missing.
    (tmp_path / "data" / "TimeDrops JSON example.json").unlink()
    for view in ("Imported Events", "Athlete Database", "Reports"):
        with patch("database.db.init_db", side_effect=AssertionError("Season module must not initialize the workflow database")):
            app.button(key="season_continue").click().run()
        assert not app.exception and not app.error
        assert app.radio(key="season_view").value == view
    assert not any(b.key == "season_continue" for b in app.button)
    for view in ("Athlete Database", "Imported Events", "Import Results"):
        assert app.button(key="season_back").label == f"← Back to {view}"
        app.button(key="season_back").click().run()
        assert not app.exception
        assert app.radio(key="season_view").value == view
    (tmp_path / "data" / "TimeDrops JSON example.json").write_text("{}", encoding="utf-8")
    app.radio(key="app_module").set_value("Event Management").run()
    assert not app.exception
    assert any(b.key == "btn_next_bottom" for b in app.button)
    assert app.session_state.current_phase == 1


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
    app.radio(key="season_view").set_value("Athlete Database").run()
    assert not app.exception
    app.checkbox[0].uncheck()
    app.button[0].click().run()
    assert not app.exception
    assert season_snapshot(db)["athletes"][0]["affiliated"] == 0
    app.radio(key="season_view").set_value("Reports").run()
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
    app.radio(key="season_view").set_value("Imported Events").run()
    assert app.selectbox(key="season_selected_year").value is None
    assert any("no confirmed season" in w.value for w in app.warning)
    assert app.button(key="season_continue").label == "Continue to Athlete Database →"
    app.button(key="season_continue").click().run()
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
    app.button(key="season_back").click().run()
    assert not any("Current season starting" in c.value for c in app.caption)


def test_reports_and_current_record_save(tmp_path, monkeypatch):
    from database.season_repository import store_event
    from parsers.season_records import validate_record_benchmarks

    app = app_test(tmp_path, monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    db = tmp_path / "data" / "season_results.sqlite"
    store_event(db, sample_event())
    app.radio(key="season_view").set_value("Reports").run()
    assert not app.exception
    assert {s.value for s in app.subheader} == {
        "Full database", "Primary schools and high schools results", "Qualified schools", "Affiliated athletes", "Qualified athletes", "Top athletes", "Records"}
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
        app.radio(key="season_view").set_value("Reports").run()
        assert not app.exception
        assert {e["season_year"] for e in reports.call_args.args[1]["events"]} == {2027}
        app.selectbox(key="season_selected_year").set_value(2026).run()
        assert not app.exception
        assert {r["season_year"] for r in reports.call_args.args[1]["results"]} == {2026}
