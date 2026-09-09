"""Published season results; no scoring or event-workflow dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re

LEAGUE = "Gauteng North Local League"
INTERPROVINCIAL = "Interprovincial"
CHAMPIONSHIP = "Gauteng North Championship"
COMPETITION_TYPES = (LEAGUE, INTERPROVINCIAL, CHAMPIONSHIP)
AWARD_TYPES = ("Runner", "Swimmer", "Overall Athlete")


def is_gn_championship(name: str) -> bool:
    return bool(re.search(r"\b(?:GN|GAUTENG\s+NORTH)\b", name, re.I)
                and re.search(r"\b(?:CHAMPIONSHIPS?|CHAMPS)\b", name, re.I))


def event_identity(name: str) -> str:
    """Ignore presentation punctuation/case, never use the source filename."""
    name = re.sub(r"inter[\s-]*provincial", "interprovincial", name.casefold())
    return " ".join(re.findall(r"\w+", name))


@dataclass
class Result:
    athlete_number: str
    athlete_name: str
    category: str
    position: str = ""
    run_time: str = ""
    running_points: str = ""
    swim_time: str = ""
    swimming_points: str = ""
    bonus_points: str = ""
    total_points: str = ""
    status: str = ""
    school: str = ""
    province: str = ""
    team: str = ""
    affiliated: bool = False
    annotations: str = ""


@dataclass
class Award:
    athlete_number: str
    athlete_name: str
    award_type: str
    placing: int
    affiliated: bool = False


@dataclass
class NormalizedEvent:
    name: str
    event_date: date | None
    competition_type: str
    source_filename: str
    results: list[Result] = field(default_factory=list)
    awards: list[Award] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def identity(self) -> str:
        return event_identity(self.name)

    def check_structure(self) -> None:
        """Check import completeness/links, not the upstream competition scores."""
        if not self.identity or not isinstance(self.event_date, date):
            raise ValueError("An event name and date are required before importing.")
        if self.competition_type not in COMPETITION_TYPES:
            raise ValueError("Select a supported competition type before importing.")
        if not self.results:
            raise ValueError("No category results were found in this file.")
        numbers = [r.athlete_number for r in self.results]
        if len(numbers) != len(set(numbers)):
            raise ValueError("Repeated athlete numbers in category results; import stopped to avoid losing rows.")
        for result in self.results:
            if not result.athlete_number or not result.athlete_name or not result.category:
                raise ValueError("A result is missing its athlete number, name or category.")
        for award in self.awards:
            if award.athlete_number not in numbers:
                raise ValueError(f"Award athlete {award.athlete_number} has no category result.")
            if award.award_type not in AWARD_TYPES or award.placing not in (1, 2, 3):
                raise ValueError("An award has an unsupported type or placing.")
