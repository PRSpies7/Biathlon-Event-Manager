"""Known heat-sheet geometry with a small, optional handwriting recognizer boundary.

A recognizer receives a pdfplumber page crop of one Time cell and returns
(text, certain). No OCR service, credentials, or network calls are configured.
"""
from io import BytesIO
import re
import pdfplumber
from services.results_verification import ManualReading


def extract_manual_pdf(payload, discipline, recognizer=None):
    readings, warnings = [], []
    with pdfplumber.open(BytesIO(payload)) as pdf:
        if not pdf.pages:
            raise ValueError('Manual PDF has no pages.')
        for page_number, page in enumerate(pdf.pages, 1):
            words = page.extract_words()
            text = page.extract_text() or ''
            if discipline == 'run' and 'Swimming Heats' in text:
                continue
            if discipline == 'swim' and 'Running Heats' in text:
                continue
            table_found = False
            if discipline == 'swim':
                for table in page.find_tables():
                    cells = table.extract()
                    header = next((i for i, row in enumerate(cells)
                                   if [str(c or '').strip() for c in row] ==
                                   ['Lane', '#', 'Athlete Name', 'Age group', 'Heat', 'Time']), None)
                    if header is None:
                        continue
                    table_found = True
                    for index in range(header + 1, len(cells)):
                        row = cells[index]
                        if len(row) != 6 or not row[1] or not row[2]:
                            continue
                        bbox = table.rows[index].cells[5]
                        if not bbox:
                            continue
                        value, certain = recognizer(page.crop(bbox)) if recognizer else (row[5] or '', False)
                        readings.append(ManualReading(str(row[1]).strip(), ' '.join(row[2].split()),
                            discipline, value.strip() or None, certain, f'Page {page_number}'))
            if table_found:
                continue
            # Headers identify columns in generated Combined Heats PDFs and in
            # PDFs printed from the six-column Swim Timekeeper workbook.
            headers = []
            for word in words:
                if word['text'] != '#':
                    continue
                band = [w for w in words if abs(w['top'] - word['top']) < 4]
                athlete = next((w for w in band if w['text'] == 'Athlete'), None)
                group = next((w for w in band if w['text'] in ('Group', 'Age')), None)
                time = next((w for w in band if w['text'] == 'Time'), None)
                if athlete and group and time:
                    headers.append((word, athlete, group, time))
            found = 0
            for index, (number_col, name_col, group_col, time_col) in enumerate(headers):
                bottom = headers[index + 1][0]['top'] if index + 1 < len(headers) else page.height - 25
                ids = [w for w in words if number_col['bottom'] < w['top'] < bottom
                       and abs(w['x0'] - number_col['x0']) < 3
                       and re.fullmatch(r'\d+', w['text'])]
                for identity in ids:
                    row_words = [w for w in words if abs(w['top'] - identity['top']) < 5]
                    name = ' '.join(w['text'] for w in row_words if name_col['x0'] - 3 <= w['x0'] < group_col['x0'] - 3)
                    if not name:
                        continue
                    bbox = (time_col['x0'] - 3, max(0, identity['top'] - 4), page.width - 20,
                            min(page.height, identity['bottom'] + 8))
                    crop = page.crop(bbox)
                    value, certain = recognizer(crop) if recognizer else (crop.extract_text() or '', False)
                    readings.append(ManualReading(identity['text'], name, discipline,
                                                  value.strip() or None, certain, f'Page {page_number}'))
                    found += 1
            if not found:
                warnings.append(f'{discipline.title()} page {page_number}: no readable athlete rows. Scanned handwriting requires manual transcription or a configured recognizer.')
    if recognizer is None:
        warnings.append(f'{discipline.title()}: automatic handwriting recognition is not available. Extracted text is unconfirmed; review it against the original PDF. Never treat a missing reading as verified.')
    return readings, warnings
