"""Shared verification and reconciliation, independent of Streamlit and PDF OCR."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata

from validation.validators import normalize_time
from parsers.season_results.common import athlete_number


def name_key(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def seconds(value):
    text = normalize_time(value) or str(value or '').strip()
    match = re.fullmatch(r'(?:(\d+):)?(\d+)(?:\.(\d{1,3}))?', text)
    if not match:
        return None
    minutes, sec, fraction = match.groups()
    if minutes is not None and int(sec) >= 60:
        return None
    total = Decimal(minutes or 0) * 60 + Decimal(sec + '.' + (fraction or '0'))
    return total if total > 0 else None


def no_start(value):
    return re.sub(r'[^A-Z]', '', str(value or '').upper()) in {'NS', 'DNS'}


def manual_value(value):
    """Compact handwritten MSS.hh is a reviewable candidate, never a silent fix."""
    text = str(value or '').strip()
    compact_digits = re.fullmatch(r'(\d{4,6})', text)
    if compact_digits:
        digits = compact_digits[1]
        return f'{int(digits[:-4] or 0)}:{digits[-4:-2]}.{digits[-2:]}', True
    compact_fraction = re.fullmatch(r'(\d{1,2})[.:](\d{4})', text)
    if compact_fraction:
        return f'{int(compact_fraction[1])}:{compact_fraction[2][:2]}.{compact_fraction[2][2:]}', True
    # Some timekeepers use a colon/comma between seconds and hundredths.
    # This alternative reading is always flagged for confirmation.
    seconds_only = re.fullmatch(r'(\d{2})[:,](\d{2})', text)
    if seconds_only and int(seconds_only[1]) < 60:
        return f'00:{seconds_only[1]}.{seconds_only[2]}', True
    text = text.replace(',', '.')
    match = re.fullmatch(r'(\d{3,4})\.(\d{1,2})', text)
    if match:
        digits, fraction = match.groups()
        return f'{int(digits[:-2])}:{digits[-2:]}.{fraction}', True
    return text, text != str(value or '').strip()


def formatted_time(value):
    total = seconds(manual_value(value)[0])
    if total is None:
        return None
    hundredths = int((total * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return f'{hundredths // 6000:02d}:{hundredths // 100 % 60:02d}.{hundredths % 100:02d}'


@dataclass(frozen=True)
class VerificationResult:
    athlete_id: str
    athlete_name: str
    run_time: str | None = None
    swim_time: str | None = None
    run_expected: bool = True
    swim_expected: bool = True


@dataclass(frozen=True)
class ManualReading:
    athlete_id: str
    athlete_name: str
    discipline: str
    time: str | None
    certain: bool = False
    source: str = ''
    preview: bytes | None = None


@dataclass(frozen=True)
class Issue:
    key: str
    athlete_id: str
    athlete_name: str
    discipline: str
    manual_time: str | None
    electronic_time: str | None
    difference: Decimal | None
    status: str
    matching: str
    target_id: str | None
    source: str = ''
    preview: bytes | None = None


def event_results(rows):
    return [VerificationResult(athlete_number(a['athlete_number']), a['athlete_name'],
        a.get('run_time'), a.get('swim_time'),
        bool(a.get('run_time') or a.get('run_entered') or a.get('running_heat')),
        bool(a.get('swim_time') or a.get('swim_entered') or a.get('swimming_heat'))) for a in rows]


def verify_results(electronic, manual):
    """Return only review issues; no fuzzy matching or automatic corrections."""
    by_id, by_name = {}, {}
    for result in electronic:
        by_id.setdefault(result.athlete_id, []).append(result)
        by_name.setdefault(name_key(result.athlete_name), []).append(result)
    matches = []
    for reading in manual:
        if reading.discipline not in ('run', 'swim'):
            raise ValueError('Unknown result type.')
        candidates = by_id.get(athlete_number(reading.athlete_id), []) if reading.athlete_id else []
        method = 'MATCHED_BY_ID'
        if not candidates:
            candidates = by_name.get(name_key(reading.athlete_name), []) if name_key(reading.athlete_name) else []
            method = 'MATCHED_BY_NAME'
        if len(candidates) != 1:
            method = 'AMBIGUOUS_MATCH' if candidates else 'NO_MATCH'
        matches.append((reading, candidates[0] if len(candidates) == 1 else None, method))
    counts = {}
    for reading, target, _ in matches:
        if target:
            key = (target.athlete_id, reading.discipline)
            counts[key] = counts.get(key, 0) + 1
    issues, seen = [], set()
    for reading, target, method in matches:
        discipline = reading.discipline
        electronic_time = getattr(target, discipline + '_time') if target else None
        candidate, compact = manual_value(reading.time)
        manual_seconds, electronic_seconds = seconds(candidate), seconds(electronic_time)
        difference = abs(manual_seconds - electronic_seconds) if manual_seconds is not None and electronic_seconds is not None else None
        if not target:
            status = method
        elif counts[(target.athlete_id, discipline)] > 1:
            status = 'DUPLICATE_MANUAL_RESULT'
        elif not str(reading.time or '').strip():
            status = 'MISSING_MANUAL_RESULT'
        elif not reading.certain:
            status = 'UNCERTAIN_RECOGNITION'
        elif no_start(reading.time):
            status = 'NO_START_CONFLICT' if electronic_seconds is not None else 'PASS'
        elif manual_seconds is None:
            status = 'UNREADABLE_MANUAL_TIME' if reading.time else 'MISSING_MANUAL_RESULT'
        elif electronic_seconds is None:
            status = 'MISSING_ELECTRONIC_RESULT'
        elif difference > Decimal('1.00'):
            status = 'HIGH_RISK'
        elif difference > Decimal('0.40'):
            status = 'TIME_DIFFERENCE'
        elif compact:
            status = 'NONSTANDARD_TIME'
        elif method == 'MATCHED_BY_NAME' and reading.athlete_id:
            status = 'ID_NOT_FOUND'
        else:
            status = 'PASS'
        if target:
            seen.add((target.athlete_id, discipline))
        if status != 'PASS':
            issues.append(Issue(str(len(issues)), target.athlete_id if target else reading.athlete_id,
                target.athlete_name if target else reading.athlete_name, discipline, reading.time,
                electronic_time, difference, status, method,
                target.athlete_id if target and status != 'DUPLICATE_MANUAL_RESULT' else None, reading.source, reading.preview))
    for result in electronic:
        for discipline in ('run', 'swim'):
            if getattr(result, discipline + '_expected') and (result.athlete_id, discipline) not in seen:
                issues.append(Issue(str(len(issues)), result.athlete_id, result.athlete_name, discipline,
                    None, getattr(result, discipline + '_time'), None, 'MISSING_MANUAL_RESULT',
                    'MATCHED_BY_ID', result.athlete_id))
    return sorted(issues, key=lambda i: (0 if i.difference is not None and i.difference > Decimal('1.00') else 1,
                                       i.athlete_id, i.discipline, i.key))


def selected_updates(issues, choices):
    updates = []
    for issue in issues:
        if choices.get(issue.key) == 'Use Manual':
            value = formatted_time(issue.manual_time)
            if not issue.target_id or (value is None and not no_start(issue.manual_time)):
                raise ValueError('Correct the athlete match or unreadable manual time and verify again.')
            updates.append((issue.target_id, issue.discipline + '_time', value))
    return updates


def reconcile_results(electronic, issues, choices):
    from dataclasses import replace
    updates = selected_updates(issues, choices)
    result = list(electronic)
    for athlete_id, field, value in updates:
        result = [replace(row, **{field: value}) if row.athlete_id == athlete_id else row for row in result]
    return result


def apply_event_results(db_path, event_id, electronic, issues, choices):
    from database.repository import get_athletes, update_manual_time
    if event_results(get_athletes(db_path, event_id)) != electronic:
        raise ValueError('Results changed since verification. Verify again before applying.')
    updates = selected_updates(issues, choices)
    for athlete_id, field, value in updates:
        # Same authoritative update path as Step 4 Save Changes. The page rerun
        # reloads the table and rebuilds exports; event results have no scoring engine.
        update_manual_time(db_path, event_id, athlete_id, field, value)
    return len(updates)
