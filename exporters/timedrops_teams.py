from __future__ import annotations

import copy
from typing import Any


INTERPROVINCIAL_TEAMS = [
    {"teamId": "1", "teamAbbreviation": "GN", "teamShortName": "GN Biathlon", "teamFullName": "Gauteng North Biathlon", "teamMascot": None},
    {"teamId": "2", "teamAbbreviation": "CG", "teamShortName": "CG Biathlon", "teamFullName": "Central Gauteng Biathlon", "teamMascot": None},
    {"teamId": "3", "teamAbbreviation": "BOL", "teamShortName": "BOL Biathlon", "teamFullName": "Boland Biathlon", "teamMascot": None},
    {"teamId": "4", "teamAbbreviation": "EDEN", "teamShortName": "EDEN Biathlon", "teamFullName": "Eden Biathlon", "teamMascot": None},
    {"teamId": "5", "teamAbbreviation": "WP", "teamShortName": "WP Biathlon", "teamFullName": "Western Province Biathlon", "teamMascot": None},
    {"teamId": "6", "teamAbbreviation": "EP", "teamShortName": "EP Biathlon", "teamFullName": "Eastern Province Biathlon", "teamMascot": None},
    {"teamId": "7", "teamAbbreviation": "BOR", "teamShortName": "BOR Biathlon", "teamFullName": "Border Biathlon", "teamMascot": None},
    {"teamId": "8", "teamAbbreviation": "SFS", "teamShortName": "SFS Biathlon", "teamFullName": "Southern Free State Biathlon", "teamMascot": None},
    {"teamId": "9", "teamAbbreviation": "NFS", "teamShortName": "NFS Biathlon", "teamFullName": "Northern Free State Biathlon", "teamMascot": None},
    {"teamId": "10", "teamAbbreviation": "GRI", "teamShortName": "GW Biathlon", "teamFullName": "Griqualand West Biathlon", "teamMascot": None},
    {"teamId": "11", "teamAbbreviation": "KZN", "teamShortName": "KZN Biathlon", "teamFullName": "KwaZulu-Natal Biathlon", "teamMascot": None},
    {"teamId": "12", "teamAbbreviation": "LIM", "teamShortName": "LIM Biathlon", "teamFullName": "Limpopo Biathlon", "teamMascot": None},
    {"teamId": "13", "teamAbbreviation": "MP", "teamShortName": "MP Biathlon", "teamFullName": "Mpumalanga Biathlon", "teamMascot": None},
    {"teamId": "14", "teamAbbreviation": "NW", "teamShortName": "NW Biathlon", "teamFullName": "North West Biathlon", "teamMascot": None},
]

TEAM_BY_PROVINCE = {team["teamAbbreviation"]: team for team in INTERPROVINCIAL_TEAMS}


def interprovincial_teams() -> list[dict[str, Any]]:
    """Return the canonical Time Drops team array without exposing mutable constants."""
    return copy.deepcopy(INTERPROVINCIAL_TEAMS)


def interprovincial_team_id(athlete: dict[str, Any]) -> str:
    """Resolve the athlete's exact supplied Province abbreviation or fail clearly."""
    athlete_id = str(athlete.get("athlete_number") or "").strip()
    athlete_name = str(athlete.get("athlete_name") or "").strip()
    province = str(athlete.get("province") or "").strip()
    athlete_label = f"{athlete_name} ({athlete_id})" if athlete_name else athlete_id
    if not province:
        raise ValueError(f"Interprovincial athlete {athlete_label} is missing a Province abbreviation.")
    team = TEAM_BY_PROVINCE.get(province)
    if team is None:
        raise ValueError(
            f"Interprovincial athlete {athlete_label} has unknown Province abbreviation '{province}'."
        )
    return str(team["teamId"])
