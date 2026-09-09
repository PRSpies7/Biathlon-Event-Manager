"""Explicit team identity filtering, independent of parsing and storage."""
from dataclasses import replace
import re

from parsers.season_results.models import INTERPROVINCIAL


def is_gn_team(team, province=""):
    value = str(team or province).upper().strip()
    return bool(re.fullmatch(r"(?:TEAM\s+)?(?:GN|GAUTENG[ -]+NORTH)(?:\s+(?:TEAM\s+)?[A-Z0-9])?", value))


def gn_event(event):
    if event.competition_type != INTERPROVINCIAL:
        return event
    results = [r for r in event.results if is_gn_team(r.team, r.province)]
    numbers = {r.athlete_number for r in results}
    return replace(event, results=results, awards=[a for a in event.awards if a.athlete_number in numbers])
