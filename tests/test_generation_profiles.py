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
                assert compatibility_tier(heat,[],discipline,"Interprovincial" if profile=="interprovincial" else None) is not None
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


@pytest.mark.parametrize("profile",["league","interprovincial"])
@pytest.mark.parametrize("gender",["GIRLS","BOYS"])
def test_young_running_compatibility_is_not_transitive(profile,gender):
    from services.competition import category_key
    for pair in (("U/08","U/09"),("U/09","U/11")):
        rows=generate_heats(entries(2,pair[0]+" "+gender)+entries(3,pair[1]+" "+gender,20),settings(),profile=profile)
        assert len(heats(rows,"run"))==1
    field=entries(2,"U/08 "+gender)+entries(3,"U/09 "+gender,20)+entries(2,"U/11 "+gender,40)
    rows=generate_heats(field,settings(),profile=profile)
    for heat in heats(rows,"run"):
        assert not {"U/08","U/11"}<={category_key(r["group_name"]) for r in heat}
    replay=generate_heats(list(reversed(field)),settings(),profile=profile)
    assert sorted(rows,key=lambda r:r["athlete_number"])==sorted(replay,key=lambda r:r["athlete_number"])


@pytest.mark.parametrize("closer",["U/09","MASTERS 60+"])
@pytest.mark.parametrize("gender",["GIRLS","BOYS"])
def test_interprovincial_u8_singleton_uses_performance_not_fixed_destination(closer,gender):
    field=entries(1,"U/08 "+gender)+entries(8,"U/09 "+gender,20)+entries(8,"MASTERS 60+ "+gender,40)
    for row in field:
        row["run_seed"]=10000 if row["group_name"].startswith(("U/08",closer)) else 30000
    rows=generate_heats(field,settings(),profile="interprovincial")
    target=next(h for h in heats(rows,"run") if any(r["athlete_number"]=="100" for r in h))
    assert len(target)==9
    assert {r["group_name"] for r in target}=={"U/08 "+gender,closer+" "+gender}


@pytest.mark.parametrize("categories",[("U/15","U/17","U/19"),("SENIOR","MASTERS 40+","MASTERS 50+")])
@pytest.mark.parametrize("gender",["GIRLS","BOYS"])
def test_interprovincial_repairs_skipped_category_tiny_heat(categories,gender):
    from services.heats import reconsider_sparse_running,category_continuity_penalty
    first=entries(1,categories[0]+" "+gender)
    middle=entries(8,categories[1]+" "+gender,20)
    last=entries(2,categories[2]+" "+gender,40)
    for row in first+middle+last:
        row["run_seed"]=10000
    original=[first+last,middle]
    assert category_continuity_penalty(original,15)==1
    repaired=reconsider_sparse_running(original,15)
    assert [len(h) for h in repaired]==[11]
    assert category_continuity_penalty(repaired,15)==0
    # Mere category adjacency cannot force a much worse relative seed fit.
    for row in middle:
        row["run_seed"]=50000
    assert category_continuity_penalty(original,15)==0


def test_sparse_cluster_can_split_mixed_remainder_between_suitable_destinations():
    from services.heats import reconsider_sparse_running
    junior=entries(7,"JNR MEN")
    masters=entries(8,"MASTERS 40+ MEN",20)
    senior=entries(1,"SENIOR MEN",40)
    older=entries(2,"MASTERS 50+ MEN",60)
    for row in junior+senior:
        row["run_seed"]=10000
    for row in masters+older:
        row["run_seed"]=30000
    result=reconsider_sparse_running([junior,masters,senior+older],15)
    assert sorted(len(h) for h in result)==[8,10]
    assert {frozenset(r["group_name"] for r in h) for h in result}=={
        frozenset(["JNR MEN","SENIOR MEN"]),frozenset(["MASTERS 40+ MEN","MASTERS 50+ MEN"])}


def test_sparse_category_can_share_two_spare_destinations_without_dismantling_them():
    field=entries(26,"U/15 GIRLS")+entries(4,"U/17 GIRLS",40)
    rows=generate_heats(field,settings(),profile="interprovincial")
    assert sorted(len(h) for h in heats(rows,"run"))==[15,15]
    assert all(sum(r["group_name"]=="U/15 GIRLS" for r in h)==13 for h in heats(rows,"run"))


def test_conservative_repair_leaves_good_groups_and_impossible_sparse_heats():
    field=entries(8,"U/15 GIRLS")+entries(7,"U/17 GIRLS",20)
    assert sorted(map(len,heats(generate_heats(field,settings(),profile="interprovincial"),"run")))==[7,8]
    field=entries(1,"U/08 GIRLS")+entries(8,"U/11 GIRLS",20)
    assert sorted(map(len,heats(generate_heats(field,settings(),profile="interprovincial"),"run")))==[1,8]


def test_sparse_repair_considers_protected_destinations_before_committing_a_nearby_pair():
    field=entries(1,"U/08 GIRLS")+entries(5,"U/09 GIRLS",20)+entries(8,"MASTERS 60+ WOMEN",40)
    for row in field:
        row["run_seed"]=30000 if row["group_name"]=="U/09 GIRLS" else 10000
    rows=generate_heats(field,settings(),profile="interprovincial")
    target=next(h for h in heats(rows,"run") if any(r["athlete_number"]=="100" for r in h))
    assert {r["group_name"] for r in target}=={"U/08 GIRLS","MASTERS 60+ WOMEN"}


def test_league_continuity_breaks_structural_ties_without_changing_swim_scoring():
    from services.heats import arrangement_rank
    young=entries(2,"U/15 GIRLS")
    middle=entries(4,"U/17 GIRLS",20)
    older=entries(2,"U/19 GIRLS",40)
    for row in young+middle+older:
        row["run_seed"]=row["swim_seed"]=10000
    skipped=[young+older,middle]
    continuous=[young+middle[:2],middle[2:]+older]
    assert arrangement_rank(continuous,"run",15,12)<arrangement_rank(skipped,"run",15,12)
    # Swimming retains its previous seed/gender/category ordering (no continuity).
    assert arrangement_rank(skipped,"swim",6,6)<arrangement_rank(continuous,"swim",6,6)


@pytest.mark.parametrize("discipline",["run","swim"])
def test_special_needs_seed_fallback_when_older_masters_are_full(discipline):
    capacity=12 if discipline=="run" else 6
    field=entries(capacity,"MASTERS 70+ WOMEN")+entries(1,"SPECIAL NEEDS FEMALE",30)+entries(capacity//2,"U/09 GIRLS",40)+entries(capacity//2,"U/11 GIRLS",60)
    for closer in ("U/09 GIRLS","U/11 GIRLS"):
        for row in field:
            row[discipline+"_seed"]=10000 if row["group_name"] in {closer,"SPECIAL NEEDS FEMALE"} else 30000
        rows=generate_heats(field,settings(),profile="league")
        target=next(h for h in heats(rows,discipline) if any(r["group_name"]=="SPECIAL NEEDS FEMALE" for r in h))
        assert {r["group_name"] for r in target}=={"SPECIAL NEEDS FEMALE",closer}


def test_special_needs_interprovincial_preference_keeps_profile_boundaries():
    field=entries(2,"SPECIAL NEEDS FEMALE")+entries(3,"MASTERS 80+ WOMEN",20)+entries(3,"U/09 GIRLS",40)
    for row in field:
        row["run_seed"]=row["swim_seed"]=30000 if row["group_name"]=="MASTERS 80+ WOMEN" else 10000
    rows=generate_heats(field,settings(),profile="interprovincial")
    for discipline in ("run","swim"):
        target=next(h for h in heats(rows,discipline) if any(r["group_name"]=="SPECIAL NEEDS FEMALE" for r in h))
        assert {r["group_name"] for r in target}=={"SPECIAL NEEDS FEMALE","MASTERS 80+ WOMEN"}
    strict=generate_heats(field,settings(),profile="sa_champs")
    assert all(len({r["group_name"] for r in h})==1 for d in ("run","swim") for h in heats(strict,d))
