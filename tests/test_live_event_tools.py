from random import Random
import pytest

from database.db import init_db
from database.repository import (create_event,replace_athletes,get_athletes,get_running_heats,
    get_run_groups,save_run_positions,insert_run_heat,update_manual_time,approve_heats,get_event)
from services.event_testing import generate_test_positions,generate_test_results,result_indicator,contains_test_data
from services.heats import generate_heats
from services.heat_outputs import current_outputs,generate_outputs
from test_heat_workflow import entries,settings


def event(tmp_path):
    db=tmp_path/"event.sqlite"
    init_db(db)
    eid=create_event(db,"Test","GN","2026-09-15","SCM",6)
    rows=generate_heats(entries(16),settings(),optimise=False)
    replace_athletes(db,eid,rows)
    return db,eid


@pytest.mark.parametrize("before",[1,2,None])
def test_insert_heat_preserves_captured_groups_results_and_invalidates_outputs(tmp_path,before):
    db,eid=event(tmp_path)
    for h in (1,2):
        members=[r for r in get_athletes(db,eid) if r["running_heat"]==h]
        save_run_positions(db,eid,[h],{r["athlete_number"]:i+1 for i,r in enumerate(members)})
    update_manual_time(db,eid,"100","run_time","01:23.45")
    approve_heats(db,eid,get_event(db,eid)["heat_revision"])
    generate_outputs(db,eid,{})
    original=get_athletes(db,eid)
    inserted=insert_run_heat(db,eid,before)
    assert inserted==(before or 3) and get_running_heats(db,eid)==[1,2,3]
    assert not current_outputs(db,eid)
    for old,new in zip(original,get_athletes(db,eid)):
        expected=old["running_heat"]+(old["running_heat"]>=inserted)
        assert new["running_heat"]==expected and new["run_group_key"]==str(expected)
        for field in ("run_time","run_position","swimming_heat","swimming_lane"):
            assert new[field]==old[field]
    assert any(g["heat_numbers"]==[inserted] for g in get_run_groups(db,eid))


def test_insert_preserves_combined_mapping_and_rejects_missing_reference(tmp_path):
    db,eid=event(tmp_path)
    rows=get_athletes(db,eid)
    save_run_positions(db,eid,[1,2],{r["athlete_number"]:i+1 for i,r in enumerate(rows)})
    insert_run_heat(db,eid,2)
    assert all(r["run_group_key"]=="1+3" for r in get_athletes(db,eid))
    before=get_athletes(db,eid)
    with pytest.raises(ValueError):
        insert_run_heat(db,eid,99)
    assert get_athletes(db,eid)==before


def test_sample_data_keeps_existing_values_and_is_marked(tmp_path):
    db,eid=event(tmp_path)
    rows=get_athletes(db,eid)
    save_run_positions(db,eid,[1,2],{r["athlete_number"]:None for r in rows})
    save_run_positions(db,eid,[1,2],{"100":4})
    update_manual_time(db,eid,"100","run_time","01:23.45")
    assert generate_test_positions(db,eid,Random(1))==15
    saved=get_athletes(db,eid)
    assert sorted(r["run_position"] for r in saved)==list(range(1,17))
    assert next(r for r in saved if r["athlete_number"]=="100")["run_position"]==4
    assert generate_test_results(db,eid,Random(1))==31
    assert generate_test_results(db,eid,Random(1))==0
    assert next(r for r in get_athletes(db,eid) if r["athlete_number"]=="100")["run_time"]=="01:23.45"
    assert contains_test_data(db,eid)
    assert all(r["run_time"] and r["swim_time"] for r in get_athletes(db,eid))


def test_result_colours_and_heat_or_category_outliers():
    row=dict(athlete_number="1",group_name="U/13 GIRLS",gender="F",running_heat=1,swimming_heat=1,run_distance=800,swim_distance=50)
    assert result_indicator(row)=="🔴"
    assert result_indicator(dict(row,run_time="02:00.00"))=="🟠"
    row.update(run_time="02:00.00",swim_time="00:40.00")
    assert result_indicator(row)=="🟢"
    assert result_indicator(dict(row,run_seed=3000))=="🟠"
    peers=[dict(row,athlete_number=str(i),run_time="00:50.00") for i in (2,3,4)]
    assert result_indicator(row,peers)=="🟠"
    assert result_indicator(row,peers[:2])=="🟢"
    for p in peers:
        p["running_heat"]=2  # Category reference still catches it.
    assert result_indicator(row,peers)=="🟠"
    for p in peers:
        p["run_distance"]=400
    assert result_indicator(row,peers)=="🟢"


def test_phase2_empty_heat_and_test_controls_smoke(tmp_path,monkeypatch):
    from test_heat_workflow_ui import opened
    app,db,eid,_=opened(tmp_path,monkeypatch,generate_heats(entries(3),settings()))
    approve_heats(db,eid,get_event(db,eid)["heat_revision"])
    app.radio(key="workflow_phase").set_value(2).run()
    app.button(key=f"insert_run_heat_{eid}").click().run()
    assert not app.exception and not app.error
    assert get_running_heats(db,eid)==[1,2]
    assert app.session_state[f"phase2_heat_{eid}"]==2
    app.checkbox(key=f"test_event_confirm_2_{eid}").check().run()
    app.button(key=f"generate_test_data_2_{eid}").click().run()
    assert not app.exception and not app.error
    app.radio(key="workflow_phase").set_value(3).run()
    app.checkbox(key=f"test_event_confirm_3_{eid}").check().run()
    app.button(key=f"generate_test_data_3_{eid}").click().run()
    assert not app.exception and not app.error
    app.radio(key="workflow_phase").set_value(4).run()
    assert not app.exception
    assert any("generated test data" in w.value for w in app.warning)
