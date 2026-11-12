from dataclasses import replace
from io import BytesIO
from unittest.mock import patch
from database.season_repository import season_snapshot
from parsers.season_results.models import INTERPROVINCIAL
from test_season_results import sample_event
from test_season_results_ui import app_test


def test_process_saves_gn_and_opens_reports(tmp_path,monkeypatch):
    app = app_test(tmp_path,monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    upload = BytesIO(b"synthetic"); upload.name = "anything.pdf"
    event = sample_event()
    event = replace(event,name="SFS IP",competition_type=INTERPROVINCIAL,
                    results=[event.results[0],replace(event.results[1],team="NW")])
    with patch("streamlit.file_uploader",side_effect=lambda label,**kw:[upload] if label == "Final results files" else None), patch("ui.season_results.parse_season_results",return_value=event):
        app.run()
        assert app.button(key="season_preview").label == "Process results"
        app.button(key="season_preview").click().run()
    assert not app.exception and not app.error
    assert app.radio(key="app_module").value == "Reports"
    assert app.selectbox(key="season_selected_year").value == 2027
    snapshot = season_snapshot(tmp_path/"data/season_results.sqlite",2027)
    assert [a["athlete_number"] for a in snapshot["athletes"]] == ["00101"]
    assert len(snapshot["awards"]) == 3
    assert any("SFS IP" in i.value for i in app.info)
    assert any("saved 1 results" in i.value for i in app.success)


def test_processing_error_does_not_block_other_files_or_overwrite(tmp_path,monkeypatch):
    app = app_test(tmp_path,monkeypatch)
    app.radio(key="app_module").set_value("Season Results Database").run()
    good,bad = BytesIO(b"good"),BytesIO(b"bad")
    good.name,bad.name = "good.pdf","bad.pdf"
    def parse(source,name):
        if name == "bad.pdf":
            raise ValueError("Unsupported data")
        return sample_event()
    with patch("streamlit.file_uploader",side_effect=lambda label,**kw:[good,bad] if label == "Final results files" else None), patch("ui.season_results.parse_season_results",side_effect=parse):
        app.run()
        app.button(key="season_preview").click().run()
        assert not app.exception
        assert app.radio(key="app_module").value == "Season Results Database"
        assert any("bad.pdf: Unsupported data" in e.value for e in app.error)
        db = tmp_path/"data/season_results.sqlite"
        before = season_snapshot(db)
        assert len(before["events"]) == 1
        app.button(key="season_preview").click().run()
        assert season_snapshot(db) == before
        assert any("already exists" in w.value for w in app.warning)
