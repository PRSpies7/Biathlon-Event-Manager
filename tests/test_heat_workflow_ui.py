"""Final acceptance smoke test of both starts through the real Streamlit UI."""
from io import BytesIO
from datetime import date
from unittest.mock import patch

import pytest

from test_season_results_ui import app_test
from test_heat_workflow import entries, settings
from services.heats import generate_heats
from exporters.heats import build_heats_xlsx
from services.heat_outputs import current_outputs
from database.repository import get_event, get_athletes, update_manual_time
from database.season_db import init_season_db
from database.season_repository import store_event, season_snapshot
from parsers.season_results.models import NormalizedEvent, Result, LEAGUE


def test_whole_heat_reordering_in_both_disciplines(tmp_path,monkeypatch):
    from database.repository import create_event,replace_athletes,approve_heats
    app=app_test(tmp_path,monkeypatch)
    db=tmp_path/"data/biathlon_events.sqlite"
    eid=create_event(db,"Move whole heats","GN","2026-09-01","SCM",6,heat_source="generated")
    rows=generate_heats(entries(25),settings(),optimise=False)
    replace_athletes(db,eid,rows)
    approve_heats(db,eid,get_event(db,eid)["heat_revision"])
    app.session_state["event_id"]=eid
    app.run()
    for discipline,prefix,source,destination in (("run","running",3,1),("swim","swimming",1,5)):
        before=get_athletes(db,eid)
        app.selectbox(key=f"move_whole_heat_{discipline}").set_value(source).run()
        target=next(w for w in app.number_input if w.key and w.key.startswith(f"whole_heat_position_{eid}_{discipline}_{source}_"))
        target.set_value(destination)
        app.button(key=f"apply_whole_heat_{discipline}").click().run()
        assert not app.exception and not app.error
        after=get_athletes(db,eid)
        for old,new in zip(before,after):
            assert old[prefix+"_lane"]==new[prefix+"_lane"]
            if old[prefix+"_heat"]==source:
                assert new[prefix+"_heat"]==destination
        assert get_event(db,eid)["heat_status"]=="stale"


def test_entry_corrections_unblock_initialization(tmp_path, monkeypatch):
    import openpyxl
    app=app_test(tmp_path,monkeypatch)
    history=tmp_path/"data/history.sqlite"
    monkeypatch.setenv("SEASON_DATABASE_PATH",str(history))
    init_season_db(history)
    store_event(history,NormalizedEvent("Prior meet",date(2026,8,1),LEAGUE,"prior.xlsx",
        [Result("100","HHeeiiddi von Wielligh","Special Needs Female",run_time="02:00.00",swim_time="00:45.00")],season_year=2027))
    event=dict(settings(),name="Entry correction",host_team="GN",start_date="2026-09-01",season_year=2027,course="SCM")
    field=entries(6,"Special Needs Female")
    field[0]["athlete_name"]="Heidi von Wielligh"
    workbook=openpyxl.load_workbook(build_heats_xlsx(generate_heats(field,event),event))
    for row in workbook.active:
        if str(row[0].value).startswith("Pool lanes:"):
            row[0].value=None  # Older accepted documents only carry occupied lanes.
    upload=BytesIO()
    workbook.save(upload)
    upload.name="Entries.xlsx"
    with patch("streamlit.file_uploader",return_value=upload):
        app.radio(key="heat_source_0").set_value("Generate heats from entries").run()
        assert not app.exception
        assert next(w for w in app.number_input if w.label=="Pool lanes").value==6
        assert not any("Run starting positions" in w.label for w in app.text_input)
        initialize=next(b for b in app.button if b.label=="Confirm Entries and Initialize Event")
        assert initialize.disabled
        assert not any(w.label.startswith("Confirm identity:") for w in app.selectbox)
        assert any("Linked by athlete number; no action required" in w.value for w in app.warning)
        next(w for w in app.checkbox if w.label.startswith("Confirm pool capacity:")).check().run()
        next(b for b in app.button if b.label=="Confirm Entries and Initialize Event").click().run()
        assert not app.exception and not app.error
        eid=app.session_state.event_id
        rows=get_athletes(tmp_path/"data/biathlon_events.sqlite",eid)
        heidi=next(r for r in rows if r["athlete_number"]=="100")
        assert heidi["athlete_name"]=="Heidi von Wielligh"
        assert (heidi["run_distance"],heidi["swim_distance"],heidi["swim_seed"])==(400,50,4500)


@pytest.mark.parametrize("generated", [True, False])
def test_both_start_paths_reach_exports_results_and_season_reports(tmp_path, monkeypatch, generated):
    app=app_test(tmp_path,monkeypatch)
    history=tmp_path/"data/history.sqlite"
    monkeypatch.setenv("SEASON_DATABASE_PATH",str(history))
    init_season_db(history)
    store_event(history,NormalizedEvent("Prior meet",date(2026,8,1),LEAGUE,"prior.xlsx",
        [Result("100","Athlete 0","U/13 GIRLS",run_time="02:30.00",swim_time="00:40.00")],season_year=2027))
    event=dict(settings(),name="UI Acceptance",host_team="GN",start_date="2026-09-01",season_year=2027,course="SCM")
    upload=BytesIO(build_heats_xlsx(generate_heats(entries(2),event),event).getvalue())
    upload.name="Master Entries.xlsx"

    def click(label):
        next(b for b in app.button if b.label==label).click().run()
        assert not app.exception, app.exception

    with patch("streamlit.file_uploader",side_effect=lambda label,*args,**kwargs: upload if label=="Master Entries Excel or PDF" else None):
        app.radio(key="heat_source_0").set_value("Generate heats from entries" if generated else "Use existing heats").run()
        assert not app.exception
        if generated:
            next(c for c in app.checkbox if c.label.startswith("Confirm pool capacity")).check()
            click("Confirm Entries and Initialize Event")
            click("Generate run and swim heats")
            app.selectbox(key="move_athlete_run").set_value("100").run()
            app.number_input(key="target_heat_run_100").set_value(4)
            app.button(key="apply_move_run").click().run()
            assert not app.exception
            app.selectbox(key="move_athlete_swim").set_value("100").run()
            app.number_input(key="target_heat_swim_100").set_value(3)
            app.button(key="apply_move_swim").click().run()
            assert not app.exception
            next(c for c in app.checkbox if c.label=="I have reviewed the running heats").check()
            next(c for c in app.checkbox if c.label=="I have reviewed the swimming heats").check()
            click("Approve final run and swim heats")
            click("Generate / regenerate operational files")
        else:
            click("Confirm Data Set and Initialize Event")
        workflow=tmp_path/"data/biathlon_events.sqlite"
        eid=app.session_state.event_id
        assert get_event(workflow,eid)["season_year"]==2027
        assert len(current_outputs(workflow,eid))==5
        if generated:
            athlete=next(a for a in get_athletes(workflow,eid) if a["athlete_number"]=="100")
            assert (athlete["running_heat"],athlete["swimming_heat"])==(4,3)
            assert athlete["run_seed"]==15000
        for phase in (2,3,4):
            app.button(key=f"side_nav_{phase}").click().run()
            assert not app.exception
        update_manual_time(workflow,eid,"100","run_time","02:29.00")
        update_manual_time(workflow,eid,"100","swim_time","00:39.00")
        app.run()
        app.button(key=f"save_history_{eid}").click().run()
        assert not app.exception and not app.error
        assert any(e["name"]=="UI Acceptance" for e in season_snapshot(history,2027)["events"])
        app.radio(key="app_module").set_value("Season Results Database").run()
        app.radio(key="season_view").set_value("Reports").run()
        assert not app.exception and not app.error
        assert app.selectbox(key="season_selected_year").value==2027
