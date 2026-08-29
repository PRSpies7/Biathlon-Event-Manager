from __future__ import annotations

import json
from pathlib import Path
import unittest

from exporters.timedrops_json import age_range_for_group, generate_timedrops_json
from parsers.master_entries import parse_master_entries


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_reference() -> dict:
    return json.loads((DATA / "TimeDrops JSON example.json").read_text(encoding="utf-8"))


def athlete(
    athlete_number: str,
    group_name: str,
    *,
    heat: int = 1,
    lane: int = 1,
    name: str | None = None,
    **extra,
) -> dict:
    return {
        "athlete_number": athlete_number,
        "athlete_name": name or f"Athlete {athlete_number}",
        "group_name": group_name,
        "swimming_heat": heat,
        "swimming_lane": lane,
        **extra,
    }


def generate(reference: dict, athletes: list[dict], meet_name: str = "Edited Event Setup Name") -> dict:
    return generate_timedrops_json(
        reference,
        athletes,
        meet_name=meet_name,
        host_team="Gauteng North Biathlon",
        start_date="2026-08-25",
        course="SCM",
        pool_lanes=8,
    )


class TimeDropsJsonTests(unittest.TestCase):
    def setUp(self):
        self.reference = load_reference()

    def test_event_metadata_uses_gender_age_groups_and_labels(self):
        cases = [
            (["U/15 GIRLS", "U/17 GIRLS"], 3, "F", 13, 16, "Girls", 100),
            (["U/09 BOYS", "U/13 BOYS"], 2, "M", 8, 12, "Boys", 50),
            (["U/13 GIRLS", "U/13 BOYS"], 2, "X", 11, 12, "Mixed", 50),
            (["JNR WOMEN", "MASTERS 50+ WOMEN"], 3, "F", 19, 59, "Ladies", 100),
            (["SENIORS MEN", "MASTERS 40+ MEN"], 3, "M", 27, 49, "Men", 100),
            (["U/17 GIRLS", "Junior Women"], 3, "F", 15, 26, "Ladies", 100),
        ]
        for groups, event_number, gender, minimum, maximum, term, distance in cases:
            with self.subTest(groups=groups):
                athletes = [
                    athlete(str(1000 + index), group, lane=index)
                    for index, group in enumerate(groups, start=1)
                ]
                event = generate(self.reference, athletes)["meetEvents"][event_number - 1]
                self.assertEqual(
                    event,
                    {
                        "eventNumber": str(event_number),
                        "eventStrokeCode": 1,
                        "eventStroke": "FREE",
                        "eventIsRelay": False,
                        "eventRelaylegs": 1,
                        "eventDistance": distance,
                        "eventGender": gender,
                        "eventMinAge": minimum,
                        "eventMaxAge": maximum,
                        "eventDescription": f"{term} Open {distance}m Freestyle",
                        "eventShortLabel": f"{term} {distance} Free",
                        "eventFullLabel": f"{term} Open {distance}m Freestyle",
                        "eventStartTime": "",
                    },
                )

    def test_all_supported_age_group_ranges_and_text_variants(self):
        expected = {
            "u8 girls": (6, 7),
            "U/09 BOYS": (8, 8),
            "U 11 Girls": (9, 10),
            "U/13 BOYS": (11, 12),
            "U/15 GIRLS": (13, 14),
            "U/17 BOYS": (15, 16),
            "U/19 GIRLS": (17, 18),
            "Junior Women": (19, 26),
            "SENIORS MEN": (27, 39),
            "Masters 40+ Women": (40, 49),
            "MASTERS 50 MEN": (50, 59),
            "Masters 60+ Women": (60, 69),
            "MASTERS 70+ MEN": (70, 79),
            "Masters 80+ Women": (80, 99),
        }
        self.assertEqual({group: age_range_for_group(group) for group in expected}, expected)

    def test_races_lanes_swimmers_and_event_setup_metadata_are_linked(self):
        athletes = [
            athlete("7409", "U/11 GIRLS", heat=4, lane=3, name="Elke Vorster"),
            athlete("8124", "U/13 GIRLS", heat=5, lane=1, name="Zoë van der Merwe", age=12),
            # A repeated source record must not duplicate meetSwimmers.
            athlete("7409", "U/11 GIRLS", heat=5, lane=2, name="Elke Vorster"),
        ]
        output = generate(self.reference, athletes)
        races = output["meetSessions"][0]["sessionRaces"]

        self.assertEqual(output["meetName"], "Edited Event Setup Name")
        self.assertEqual(output["meetHostTeamName"], "Gauteng North Biathlon")
        self.assertEqual(output["meetStartDate"], "2026-08-25")
        self.assertEqual(
            output["meetSessions"][0]["sessionPool"],
            {"poolNumberOfLanes": 8, "poolCourse": "SCM", "poolFirstLaneNumber": 1},
        )
        self.assertEqual(
            [(race["raceNumber"], race["raceEventNumber"], race["raceTotalHeats"]) for race in races],
            [(4, "2", 2), (5, "2", 2)],
        )
        self.assertEqual(
            [
                (lane["laneNumber"], lane["laneEventNumber"], lane["laneSwimmerId"])
                for lane in races[1]["raceLanes"]
            ],
            [(1, "2", "8124"), (2, "2", "7409")],
        )
        self.assertEqual({swimmer["swimmerId"] for swimmer in output["meetSwimmers"]}, {"7409", "8124"})

        swimmers = {swimmer["swimmerId"]: swimmer for swimmer in output["meetSwimmers"]}
        self.assertEqual(
            swimmers["7409"],
            {
                "swimmerId": "7409",
                "swimmerName": "Elke Vorster (7409)",
                "swimmerGender": "F",
                "swimmerAge": 9,
                "swimmerTeamId": "1",
            },
        )
        self.assertEqual(swimmers["8124"]["swimmerName"], "Zoe van der Merwe (8124)")
        self.assertEqual(swimmers["8124"]["swimmerAge"], 12)

    def test_real_source_preserves_special_needs_lanes_and_uses_only_swim_assignments(self):
        parsed = parse_master_entries(DATA / "Master Entries Excel.xlsx")
        output = generate(self.reference, parsed["athletes"])
        races = output["meetSessions"][0]["sessionRaces"]

        self.assertEqual(len(races), len(parsed["swimming_heats"]))
        self.assertEqual(len(races), 18)
        self.assertEqual({race["raceNumber"] for race in races}, set(parsed["swimming_heats"]))
        self.assertEqual(sum(len(race["raceLanes"]) for race in races), len(parsed["swimming_records"]))
        self.assertEqual(output["meetEvents"][0]["eventGender"], "X")
        self.assertEqual((output["meetEvents"][1]["eventMinAge"], output["meetEvents"][1]["eventMaxAge"]), (8, 79))
        self.assertEqual((output["meetEvents"][2]["eventMinAge"], output["meetEvents"][2]["eventMaxAge"]), (13, 59))

    def test_team_metadata_reuses_reference_names_and_consistent_id(self):
        output = generate(self.reference, [athlete("1001", "U/08 GIRLS")])

        self.assertEqual(
            output["meetTeams"],
            [
                {
                    "teamId": "1",
                    "teamAbbreviation": "",
                    "teamShortName": "Gauteng North",
                    "teamFullName": "Gauteng North Biathlon",
                    "teamMascot": None,
                }
            ],
        )
        self.assertEqual(output["meetSwimmers"][0]["swimmerTeamId"], "1")
        self.assertEqual(output["meetSessions"][0]["sessionRaces"][0]["raceLanes"][0]["laneTeamId"], "1")

    def test_interprovincial_teams_and_lane_swimmer_ids_use_province(self):
        athletes = [
            athlete("1001", "U/08 GIRLS (25m)", lane=1, province="GN"),
            athlete("1002", "U/08 GIRLS (25m)", lane=2, province="CG"),
            athlete("1003", "U/08 GIRLS (25m)", lane=3, province="GRI"),
            athlete("1004", "U/08 GIRLS (25m)", lane=4, province="LIM"),
            athlete("1005", "U/08 GIRLS (25m)", lane=5, province="NW"),
        ]
        output = generate_timedrops_json(
            self.reference,
            athletes,
            meet_name="Interprovincial",
            host_team="Gauteng North Biathlon",
            start_date="2026-08-25",
            course="LCM",
            pool_lanes=8,
            meet_type="Interprovincial",
        )

        self.assertEqual(len(output["meetTeams"]), 14)
        self.assertEqual(
            [(team["teamId"], team["teamAbbreviation"]) for team in output["meetTeams"]],
            [(str(number), abbreviation) for number, abbreviation in enumerate(
                ["GN", "CG", "BOL", "EDEN", "WP", "EP", "BOR", "SFS", "NFS", "GRI", "KZN", "LIM", "MP", "NW"],
                start=1,
            )],
        )
        expected = {"1001": "1", "1002": "2", "1003": "10", "1004": "12", "1005": "14"}
        lane_ids = {
            lane["laneSwimmerId"]: lane["laneTeamId"]
            for lane in output["meetSessions"][0]["sessionRaces"][0]["raceLanes"]
        }
        swimmer_ids = {row["swimmerId"]: row["swimmerTeamId"] for row in output["meetSwimmers"]}
        self.assertEqual(lane_ids, expected)
        self.assertEqual(swimmer_ids, expected)

    def test_interprovincial_unknown_or_missing_province_fails_clearly(self):
        for province, message in [(None, "missing a Province"), ("XX", "unknown Province")]:
            with self.subTest(province=province):
                with self.assertRaisesRegex(ValueError, message):
                    generate_timedrops_json(
                        self.reference,
                        [athlete("1001", "U/08 GIRLS (25m)", province=province)],
                        meet_name="Interprovincial",
                        host_team="Host",
                        start_date="2026-08-25",
                        course="LCM",
                        pool_lanes=8,
                        meet_type="Interprovincial",
                    )


if __name__ == "__main__":
    unittest.main()
