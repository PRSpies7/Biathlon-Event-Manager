"""Batch-form review acceptance through the real Streamlit UI."""
from io import BytesIO
from datetime import date
from unittest.mock import patch
import json
import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetState
from test_season_results_ui import app_test
from test_heat_workflow import entries, settings
from database.repository import create_event,replace_athletes,get_event,get_athletes,approve_heats,update_event
from database.season_db import init_season_db
from database.season_repository import store_event,season_snapshot
from parsers.season_results.models import NormalizedEvent,Result,LEAGUE
from services.heats import generate_heats
from services.heat_outputs import current_outputs,generate_outputs
from exporters.heats import build_heats_xlsx


def table(app,prefix):
    return next(t for t in app.dataframe if prefix in t.proto.id)


def submit(app,button,edits=None):
    app.button(key=button).click()
    states=app._tree.get_widget_states()
    for prefix,changes in (edits or {}).items():
        editor=table(app,prefix)
        states.widgets.append(WidgetState(id=editor.proto.id,string_value=json.dumps(
            {"edited_rows":changes,"added_rows":[],"deleted_rows":[]})))
    app._run(widget_state=states)
    assert not app.exception,app.exception


def opened(tmp_path,monkeypatch,rows):
    history=tmp_path/"history.sqlite"
    monkeypatch.setenv("SEASON_DATABASE_PATH",str(history))
    init_season_db(history)
    app=app_test(tmp_path,monkeypatch)
    monkeypatch.setenv("SEASON_DATABASE_PATH",str(history))
    db=tmp_path/"data/biathlon_events.sqlite"
    eid=create_event(db,"Review","GN","2026-09-01","SCM",6,heat_source="generated")
    replace_athletes(db,eid,rows)
    app.session_state["event_id"]=eid
    app.run()
    assert not app.exception
    return app,db,eid,history


def test_form_batches_both_disciplines_and_remembers_swimming(tmp_path,monkeypatch):
    app,db,eid,_=opened(tmp_path,monkeypatch,generate_heats(entries(13),settings(),optimise=False))
    before=get_athletes(db,eid)
    assert not any(s.value=="Saved entries, heats and seeds" for s in app.subheader)
    run=table(app,f"heat_editor_{eid}_run_")
    swim=table(app,f"heat_editor_{eid}_swim_")
    assert "Start position" not in run.value and "Seed source" not in run.value
    assert "Seed" in run.value and "Seed" in swim.value and "Lane" in swim.value
    programme=table(app,f"programme_editor_{eid}_run_")
    assert "New Position" in programme.value and "Combine" in programme.value and "Delete" not in programme.value
    # The form explicitly disables Enter submission; edits have no callbacks.
    form=next(f for f in app.get("form") if f.proto.form.form_id==f"heat_review_form_{eid}")
    assert form.proto.form.enter_to_submit is False
    identifiers=(run.value.iloc[0]["Athlete"],swim.value.iloc[0]["Athlete"])
    submit(app,"save_heats_swim",{f"heat_editor_{eid}_run_":{0:{"Heat":9}},f"heat_editor_{eid}_swim_":{0:{"Heat":9}}})
    assert not app.error,[e.value for e in app.error]
    saved={r["athlete_number"]:r for r in get_athletes(db,eid)}
    assert saved[identifiers[0]]["running_heat"]==3
    assert saved[identifiers[1]]["swimming_heat"]==3
    assert app.session_state[f"heat_review_active_{eid}"]=="Swimming heats"
    assert app.session_state[f"heat_review_tabs_{eid}"]=="Swimming heats"
    submit(app,f"discard_heats_{eid}")
    assert app.session_state[f"heat_review_tabs_{eid}"]=="Swimming heats"
    assert len(saved)==len(before)


@pytest.mark.parametrize("discipline,prefix,count",[("run","running",25),("swim","swimming",12)])
def test_checkbox_combine_three_heats_is_draft_then_saves_fastest_last(tmp_path,monkeypatch,discipline,prefix,count):
    rows=generate_heats(entries(count),settings(),optimise=False)
    if discipline=="swim":
        for i,r in enumerate(rows):
            r.update(swimming_heat=i//4+1,swimming_lane=i%4+1)
    rows[-1][discipline+"_seed"]=None
    app,db,eid,_=opened(tmp_path,monkeypatch,rows)
    before=get_athletes(db,eid)
    submit(app,f"combine_heats_{discipline}",{f"programme_editor_{eid}_{discipline}_":{i:{"Combine":True} for i in range(3)}})
    assert not app.error,[e.value for e in app.error]
    assert get_athletes(db,eid)==before
    draft=table(app,f"heat_editor_{eid}_{discipline}_").value
    assert draft.loc[draft["Seed"]=="NT","Heat"].item()==1
    assert len(table(app,f"programme_editor_{eid}_{discipline}_").value)==(3 if discipline=="run" else 2)
    submit(app,f"save_heats_{discipline}")
    assert not app.error,[e.value for e in app.error]
    saved=get_athletes(db,eid)
    seeded=[r for r in saved if r.get(discipline+"_seed") is not None]
    assert min(seeded,key=lambda r:r[discipline+"_seed"])[prefix+"_heat"]==max(r[prefix+"_heat"] for r in saved)
    assert max(sum(r[prefix+"_heat"]==h for r in saved) for h in {r[prefix+"_heat"] for r in saved})<=(12 if discipline=="run" else 6)


def test_add_remove_duplicates_history_and_stale_outputs(tmp_path,monkeypatch):
    app,db,eid,history=opened(tmp_path,monkeypatch,generate_heats(entries(8),settings()))
    store_event(history,NormalizedEvent("Prior",date(2026,8,1),LEAGUE,"prior.xlsx",
        [Result("999","Athlete 0","U/13 GIRLS",run_time="02:00.00",swim_time="00:35.00")],season_year=2027))
    approve_heats(db,eid,get_event(db,eid)["heat_revision"])
    generate_outputs(db,eid,{})
    app.run()
    app.text_input(key=f"late_number_{eid}").set_value("999")
    app.text_input(key=f"late_name_{eid}").set_value("Athlete 0")
    app.selectbox(key=f"late_category_{eid}").set_value("U/13")
    submit(app,f"add_athlete_{eid}")
    assert not app.error
    assert any("Same full name" in w.value for w in app.warning)
    assert len(get_athletes(db,eid))==8
    submit(app,"save_heats_swim")
    assert not app.error,[e.value for e in app.error]
    late=next(r for r in get_athletes(db,eid) if r["athlete_number"]=="999")
    assert (late["run_seed"],late["swim_seed"])==(12000,3500)
    assert get_event(db,eid)["heat_status"]=="stale" and not current_outputs(db,eid)
    athletes=table(app,f"heat_editor_{eid}_run_").value
    index=int(athletes.index[athletes["Athlete"]=="999"][0])
    submit(app,"save_heats_run",{f"heat_editor_{eid}_run_":{index:{"Remove from event":True}}})
    assert not app.error
    assert len(get_athletes(db,eid))==8
    assert len(season_snapshot(history)["results"])==1
    assert not any("Same full name" in w.value for w in app.warning)


def test_add_discard_and_multiple_new_positions(tmp_path,monkeypatch):
    app,db,eid,_=opened(tmp_path,monkeypatch,generate_heats(entries(25),settings()))
    before=get_athletes(db,eid)
    submit(app,"add_heat_run")
    assert len(table(app,f"programme_editor_{eid}_run_").value)==4
    submit(app,f"discard_heats_{eid}")
    assert len(table(app,f"programme_editor_{eid}_run_").value)==3
    assert get_athletes(db,eid)==before
    submit(app,"save_heats_run",{f"programme_editor_{eid}_run_":{0:{"New Position":3},1:{"New Position":2}}})
    assert not app.error
    for old,new in zip(before,get_athletes(db,eid)):
        assert new["running_heat"]=={1:3,2:2,3:1}[old["running_heat"]]


def test_drafts_detect_external_changes_and_clear_on_session_reset(tmp_path,monkeypatch):
    app,db,eid,_=opened(tmp_path,monkeypatch,generate_heats(entries(8),settings()))
    submit(app,"add_heat_run")
    update_event(db,eid,name="Externally renamed")
    app.run()
    assert any("saved event changed" in w.value for w in app.warning)
    app.button(key=f"reload_heat_drafts_{eid}").click().run()
    submit(app,"add_heat_run")
    app.button(key="reset_sessions").click().run()
    app.button(key="confirm_reset_sessions_button").click().run()
    assert not app.exception and get_event(db,eid) is None
    assert f"heat_review_tables_{eid}" not in app.session_state


@pytest.mark.parametrize("generated",[True,False])
def test_both_start_paths_and_output_regeneration_preserve_edits(tmp_path,monkeypatch,generated):
    history=tmp_path/"history.sqlite"
    monkeypatch.setenv("SEASON_DATABASE_PATH",str(history))
    init_season_db(history)
    app=app_test(tmp_path,monkeypatch)
    event=dict(settings(),name="Acceptance",host_team="GN",start_date="2026-09-01",season_year=2027,course="SCM")
    upload=BytesIO(build_heats_xlsx(generate_heats(entries(2),event),event).getvalue())
    upload.name="Entries.xlsx"
    def click(label):
        next(b for b in app.button if b.label==label).click().run()
        assert not app.exception and not app.error,[e.value for e in app.error]
    with patch("streamlit.file_uploader",side_effect=lambda label,*a,**k: upload if label=="Master Entries Excel or PDF" else None):
        app.radio(key="heat_source_0").set_value("Generate heats from entries" if generated else "Use existing heats").run()
        if generated:
            next(c for c in app.checkbox if c.label.startswith("Confirm pool capacity")).check()
            click("Confirm Entries and Initialize Event")
            click("Generate heats from entries")
            eid=app.session_state.event_id
            submit(app,"save_heats_swim",{f"heat_editor_{eid}_run_":{0:{"Heat":4}},f"heat_editor_{eid}_swim_":{0:{"Heat":3}}})
            next(c for c in app.checkbox if c.label=="I have reviewed the running heats").check()
            next(c for c in app.checkbox if c.label=="I have reviewed the swimming heats").check()
            click("Approve final run and swim heats")
            click("Generate operational files")
        else:
            click("Confirm Data Set and Initialize Event")
        db=tmp_path/"data/biathlon_events.sqlite"
        eid=app.session_state.event_id
        before=get_athletes(db,eid)
        with patch("services.heats.generate_heats",side_effect=AssertionError("Output generation must preserve assignments")):
            click("Regenerate operational files")
        assert get_athletes(db,eid)==before and len(current_outputs(db,eid))==5
        for phase in (2,3,4):
            app.button(key=f"side_nav_{phase}").click().run()
            assert not app.exception
