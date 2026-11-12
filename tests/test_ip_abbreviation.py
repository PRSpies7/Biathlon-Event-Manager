from dataclasses import replace
from datetime import date
import pytest
from parsers.season_results import parse_season_results
from parsers.season_results.models import INTERPROVINCIAL, is_interprovincial_name
from test_season_results import pdf_fixture


@pytest.mark.parametrize("filename",["results.pdf","renamed-document.pdf","SFS IP_Results_2026-10-03.pdf"])
def test_ip_abbreviation_uses_document_not_filename(filename):
    event = parse_season_results(pdf_fixture(True,title="SFS IP"),filename)
    event.check_structure()
    assert event.name == "SFS IP"
    assert event.event_date == date(2026,8,25)
    assert event.competition_type == INTERPROVINCIAL
    assert event.results[0].athlete_name == "Alex Example"
    assert event.results[0].team == "GN Team A"
    assert len(event.awards) == 3
    assert not event.notes


@pytest.mark.parametrize("name",["Championship","Participation","Trip results"])
def test_ip_is_a_standalone_abbreviation(name):
    assert not is_interprovincial_name(name)


def test_team_table_with_unknown_title_is_readable_but_needs_confirmation():
    event = parse_season_results(pdf_fixture(True,title="Regional Results"),"random.pdf")
    assert len(event.results) == 1
    assert event.competition_type == ""
    assert event.notes
