"""Electronic inputs for shared verification; published formats use existing parsers."""
from pathlib import Path
from io import BytesIO
from xml.etree import ElementTree

from parsers.season_results import parse_season_results
from parsers.season_results.common import athlete_number
from services.results_verification import VerificationResult, name_key


def parse_electronic_results(payload: bytes, filename: str):
    if Path(filename).suffix.lower() == '.xlsx':
        # The app's five-column Master Results export is not a published season
        # report (no categories or points). Adapt only this exact extra format.
        import openpyxl
        workbook = openpyxl.load_workbook(BytesIO(payload), read_only=True, data_only=True)
        try:
            rows = workbook.active.iter_rows(values_only=True)
            header = next(rows, ())
            if tuple(header) == ('Athlete nr', 'Athlete Name', 'athleteSurname', 'runtime', 'swimtime'):
                results = [VerificationResult(athlete_number(row[0]), str(row[1] or ''), row[3], row[4])
                           for row in rows if row[0] is not None]
                if not results:
                    raise ValueError('No final results were found in the workbook.')
                return results
        finally:
            workbook.close()
    if Path(filename).suffix.lower() != '.xml':
        event = parse_season_results(BytesIO(payload), filename)
        return [VerificationResult(r.athlete_number, r.athlete_name, r.run_time, r.swim_time) for r in event.results]
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('XML document declarations and entities are not supported.')
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError('Invalid final-results XML.') from exc
    if root.tag != 'results':
        raise ValueError('Expected the final-results XML results element.')
    results = []
    for row in root.findall('result'):
        name, surname = (row.findtext(field, '').strip() for field in ('athleteName', 'athleteSurname'))
        # Some exports repeat the full name in both fields, others supply a surname.
        if surname and name_key(surname) != name_key(name) and not name_key(name).endswith(' ' + name_key(surname)):
            name = (name + ' ' + surname).strip()
        results.append(VerificationResult(athlete_number(row.findtext('athleteNo')), name,
                                          row.findtext('runtime'), row.findtext('swimtime')))
    if not results:
        raise ValueError('No final results were found in this XML.')
    return results
