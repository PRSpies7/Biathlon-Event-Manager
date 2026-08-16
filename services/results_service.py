from __future__ import annotations

from collections import defaultdict
from typing import Any

from database.repository import get_athletes, get_run_groups, update_run_times, update_swim_times
from validation.validators import normalize_time


def resolve_group_for_block(block: dict[str, Any], athletes: list[dict[str, Any]], run_groups: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    heat_set = set(block["heat_numbers"])
    issues: list[str] = []
    exact = [g for g in run_groups if set(g["heat_numbers"]) == heat_set]
    if len(exact) == 1:
        return exact[0]["group_key"], issues
    if len(exact) > 1:
        return None, [f"Multiple saved Phase 2 run groups exactly match {sorted(heat_set)}."]

    containing = [g for g in run_groups if heat_set and heat_set.issubset(set(g["heat_numbers"]))]
    if len(containing) == 1:
        issues.append(
            f"Run file section {block['label']} is mapped to saved Phase 2 group "
            f"{containing[0]['group_key']} because its heat(s) are part of that group."
        )
        return containing[0]["group_key"], issues
    if len(containing) > 1:
        return None, [f"Ambiguous Phase 2 run-group mapping for {block['label']}; multiple saved groups contain {sorted(heat_set)}."]
    return None, [f"No Phase 2 run-position mapping exists for {block['label']}. Valid results from other mapped heats will still be saved."]


def process_run_results(db_path: str, event_id: int, run_data: dict[str, Any]) -> dict[str, Any]:
    """Process run results independently and commit valid mappings to SQLite."""
    athletes = get_athletes(db_path, event_id)
    run_groups = get_run_groups(db_path, event_id)
    master_heats = sorted({int(a["running_heat"]) for a in athletes if a.get("running_heat") is not None})
    imported_heats = sorted(set(run_data.get("imported_heat_numbers", [])))

    warnings: list[str] = []
    issues: list[str] = []
    missing_heats = [h for h in master_heats if h not in imported_heats]
    unexpected_heats = [h for h in imported_heats if h not in master_heats]
    if missing_heats:
        warnings.append(
            f"Run Results file is missing heat section(s): {', '.join(map(str, missing_heats))}. "
            "This may indicate a combined heat or a heat that did not take place."
        )
    elif len(run_data.get("blocks", [])) < len(master_heats):
        warnings.append(
            f"Run Results file contains {len(run_data.get('blocks', []))} result dataset(s) for "
            f"{len(master_heats)} planned heats, but all planned heat numbers were identified. "
            "One or more result datasets may represent combined heats."
        )
    combined_labels = [
        b["label"] for b in run_data.get("blocks", [])
        if len(b.get("heat_numbers", ())) > 1
    ]
    if combined_labels:
        warnings.append(
            "Combined run heat label(s) detected: " + ", ".join(combined_labels)
            + ". All heat numbers named by these labels are treated as present."
        )
    if unexpected_heats:
        warnings.append(
            f"Run Results file contains unexpected heat section(s): {', '.join(map(str, unexpected_heats))}."
        )

    matched_run: dict[str, str] = {}
    for block in run_data.get("blocks", []):
        group_key, group_issues = resolve_group_for_block(block, athletes, run_groups)
        issues.extend(group_issues)
        if not group_key:
            continue

        group_athletes = [
            a for a in athletes
            if a.get("run_group_key") == group_key and a.get("run_position") is not None
        ]
        # Position is only meaningful within its heat/group. Never use position globally.
        pos_map = {int(a["run_position"]): a["athlete_number"] for a in group_athletes}

        for record in block.get("results", []):
            try:
                position = int(record["position"])
            except (TypeError, ValueError):
                issues.append(f"Invalid run position in {block.get('label', 'run section')}: {record.get('position')!r}.")
                continue
            athlete_number = pos_map.get(position)
            if not athlete_number:
                issues.append(
                    f"Run position {position} in {block['label']} could not be mapped to a Phase 2 athlete."
                )
                continue
            runtime = normalize_time(record.get("run_time"))
            if runtime is None:
                issues.append(
                    f"Invalid runtime for position {position} in {block['label']}: {record.get('run_time')!r}."
                )
                continue
            if athlete_number in matched_run:
                issues.append(f"Athlete {athlete_number} received multiple run times from the imported file.")
                continue
            matched_run[athlete_number] = runtime

    if matched_run:
        update_run_times(db_path, event_id, matched_run)

    source_timed_count = int(run_data.get("source_timed_count", sum(
        len(b.get("results", [])) for b in run_data.get("blocks", [])
    )))
    return {
        "ok": bool(matched_run) or not run_data.get("blocks"),
        "warnings": warnings,
        "issues": issues,
        "matched_run": matched_run,
        "matched_count": len(matched_run),
        "source_timed_count": source_timed_count,
        "uncommitted_count": max(0, source_timed_count - len(matched_run)),
        "saved": bool(matched_run),
    }


def process_swim_results(db_path: str, event_id: int, swim_data: dict[str, Any]) -> dict[str, Any]:
    """Process swim results independently and commit valid athlete-number matches to SQLite."""
    athletes = get_athletes(db_path, event_id)
    master_ids = {str(a["athlete_number"]).strip() for a in athletes}
    issues: list[str] = []
    matched_swim: dict[str, str] = {}

    for aid, record in swim_data.get("athlete_results", {}).items():
        aid = str(aid).strip()
        if aid not in master_ids:
            issues.append(f"Swim result for unknown athlete {aid}.")
            continue
        swimtime = normalize_time(record.get("swim_time"))
        if swimtime is None:
            # A zero/no-time result is not a valid final swim time, so do not write it.
            continue
        if aid in matched_swim:
            issues.append(f"Athlete {aid} received multiple swim times from the imported file.")
            continue
        matched_swim[aid] = swimtime

    if matched_swim:
        update_swim_times(db_path, event_id, matched_swim)

    source_swim_count = int(
        swim_data.get(
            "source_result_count",
            len(swim_data.get("athlete_results", {})),
        )
    )
    return {
        "ok": True,
        "warnings": [],
        "issues": issues,
        "matched_swim": matched_swim,
        "matched_count": len(matched_swim),
        "source_result_count": source_swim_count,
        "uncommitted_count": max(0, source_swim_count - len(matched_swim)),
        "saved": bool(matched_swim),
    }


def process_results(
    db_path: str,
    event_id: int,
    run_data: dict[str, Any] | None = None,
    swim_data: dict[str, Any] | None = None,
    acknowledge_heat_discrepancies: bool = False,
) -> dict[str, Any]:
    """Backward-compatible combined processor. V1.2 UI uses the independent processors."""
    run_data = run_data or {}
    swim_data = swim_data or {}
    run_result = process_run_results(db_path, event_id, run_data) if run_data else {"matched_run": {}, "issues": [], "warnings": []}
    swim_result = process_swim_results(db_path, event_id, swim_data) if swim_data else {"matched_swim": {}, "issues": [], "warnings": []}
    return {
        "ok": True,
        "requires_ack": False,
        "heat_warnings": run_result.get("warnings", []),
        "warnings": run_result.get("warnings", []) + swim_result.get("warnings", []),
        "issues": run_result.get("issues", []) + swim_result.get("issues", []),
        "matched_run": run_result.get("matched_run", {}),
        "matched_swim": swim_result.get("matched_swim", {}),
    }
