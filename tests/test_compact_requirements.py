import pytest
from services.season_reports import compact_qualification_requirements


@pytest.mark.parametrize("description,expected",[
    ("2 more completed events; including at least 1 interprovincial or Gauteng North Championship; Best completed score of at least 1890 points required",
     "+2 events: 1 IP/Champs + 1 League; Score 1890+"),
    ("1 more completed event; including at least 1 interprovincial or Gauteng North Championship",
     "+1 event: 1 IP/Champs"),
    ("1 interprovincial or Gauteng North Championship","+1 event: 1 IP/Champs"),
    ("2 more completed events","+2 events"),
    ("Best completed score of at least 1790 points required","Score 1790+"),
    ("None","None"),
    ("+2 events: 1 IP/Champs + 1 League; Score 1890+","+2 events: 1 IP/Champs + 1 League; Score 1890+"),
])
def test_compact_requirements_preserve_outstanding_needs(description,expected):
    assert compact_qualification_requirements(description) == expected
