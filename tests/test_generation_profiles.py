"""Real League validation examples, profile provenance and hard boundaries."""
import json
import sqlite3
import pytest
from test_heat_workflow import entries,settings
from services.heats import generate_heats,compatibility_tier
from database.db import init_db
from database.repository import create_event,replace_athletes,get_event,get_athletes,save_heat_assignments,approve_heats


def heats(rows,discipline):
    field={"run":"running_heat","swim":"swimming_heat"}[discipline]
    return [[r for r in rows if r[field]==h] for h in sorted({r[field] for r in rows})]


@pytest.mark.parametrize("groups,expected",[
    ([(8,"MASTERS 60+ WOMEN"),(2,"SPECIAL NEEDS FEMALE")],[10]),
    ([(14,"U/13 GIRLS")],[14]),
    ([(8,"U/15 BOYS"),(7,"U/17 BOYS")],[15]),
    ([(16,"U/13 GIRLS")],[8,8]),
    ([(25,"U/11 GIRLS")],[8,8,9]),
])
def test_league_running_distance_capacities(groups,expected):
    field=[r for i,(count,group) in enumerate(groups) for r in entries(count,group,i*100)]
    rows=generate_heats(field,settings(),profile="league")
    assert sorted(map(len,heats(rows,"run")))==expected
    for heat in heats(rows,"run"):
        assert len(heat)<=(12 if heat[0]["run_distance"]==400 else 15)
        assert compatibility_tier(heat,[],"run") is not None
        assert max(r["running_lane"] for r in heat)==len(heat)


@pytest.mark.parametrize("counts,expected",[([5,5,6,2],3),([5,5,8,6],4)])
def test_league_repacks_whole_swimming_cluster(counts,expected):
    groups=["JNR WOMEN","SENIOR WOMEN","MASTERS 40+ WOMEN","MASTERS 50+ WOMEN"]
    field=[r for i,(count,group) in enumerate(zip(counts,groups)) for r in entries(count,group,i*100)]
    # Overlap category seed bands, including a deterministic unseeded athlete.
    for i,r in enumerate(field):
        r["swim_seed"]=None if i==0 else 3000+(i*7%len(field))*100
    rows=generate_heats(field,settings(),profile="league")
    pools=heats(rows,"swim")
    assert len(pools)==expected and all(len(h)==6 for h in pools)
    assert pools[0][0]["swimming_heat"]==next(r["swimming_heat"] for r in rows if r["swim_seed"] is None)
    for slow,fast in zip(pools,pools[1:]):
        assert min(r["swim_seed"] for r in slow if r["swim_seed"] is not None)>=max(r["swim_seed"] for r in fast)
    replay=generate_heats(list(reversed(field)),settings(),profile="league")
    assert sorted(rows,key=lambda r:r["athlete_number"])==sorted(replay,key=lambda r:r["athlete_number"])
    conservative=generate_heats(field,settings(),profile="interprovincial")
    assert len(heats(conservative,"swim"))>expected


def test_profiles_keep_distance_and_forbidden_category_boundaries():
    field=entries(5,"U/09 GIRLS")+entries(5,"MASTERS 60+ WOMEN",100)+entries(2,"SPECIAL NEEDS FEMALE",200)+entries(3,"U/08 BOYS",300)
    for profile in ("league","interprovincial","sa_champs"):
        rows=generate_heats(field,settings(),profile=profile)
        for discipline in ("run","swim"):
            for heat in heats(rows,discipline):
                assert len({r[discipline+"_distance"] for r in heat})==1
                assert compatibility_tier(heat,[],discipline) is not None
                if profile=="sa_champs":
                    assert len({(r["group_name"],r["gender"]) for r in heat})==1


def test_profile_migration_and_atomic_revision_provenance(tmp_path):
    db=tmp_path/"event.sqlite"
    init_db(db)
    eid=create_event(db,"League","GN","2026-09-01","SCM",6)
    field=entries(4)+entries(2,"U/13 BOYS",20)
    replace_athletes(db,eid,generate_heats(field,settings()))
    before=get_athletes(db,eid)
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE events DROP COLUMN generation_metadata")
    init_db(db)
    assert get_athletes(db,eid)==before
    assert get_event(db,eid)["generation_metadata"] is None
    assert list(tmp_path.glob("*.before-seasons-*.sqlite"))
    event=get_event(db,eid)
    rows=generate_heats(field,event,profile="interprovincial")
    save_heat_assignments(db,eid,rows,event["heat_revision"],generation_profile="interprovincial")
    event=get_event(db,eid)
    metadata=json.loads(event["generation_metadata"])
    assert metadata=={"profile":"interprovincial","revision":event["heat_revision"]}
    assert event["meet_type"]=="Local"
    approve_heats(db,eid,event["heat_revision"])
    save_heat_assignments(db,eid,get_athletes(db,eid),event["heat_revision"])
    assert get_event(db,eid)["generation_metadata"]==event["generation_metadata"]
    with pytest.raises(ValueError,match="another session"):
        save_heat_assignments(db,eid,rows,-1,generation_profile="league")
    assert get_event(db,eid)["generation_metadata"]==event["generation_metadata"]
