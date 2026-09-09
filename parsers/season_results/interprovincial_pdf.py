"""Read IP report columns from headers and rows from horizontal rules.

Unlike league PDFs, these reports have no vertical rules through result rows.
Header cell geometry supplies the columns for each section. A row may continue
on the next page; its name/team fragments must be joined before normalization.
"""
from __future__ import annotations

from .common import header_mapping, normalize_rows, recognize_metadata, text
from .models import INTERPROVINCIAL


def _bands(page, top, bottom, columns):
    cuts = [top, bottom]
    for edge in page.edges:
        if edge.get("orientation") == "h" and edge["x1"] - edge["x0"] > 10:
            y = float(edge["top"])
            if top < y < bottom and edge["x0"] >= columns[0] - 2 and edge["x1"] <= columns[-1] + 2:
                cuts.append(y)
    merged = []
    for y in sorted(cuts):
        if not merged or y - merged[-1] > 2:
            merged.append(y)
    words = page.extract_words(x_tolerance=1, y_tolerance=2)
    for start, end in zip(merged, merged[1:]):
        cells = [[] for _ in columns[:-1]]
        for word in words:
            if not start <= (word["top"] + word["bottom"]) / 2 < end:
                continue
            for i, (left, right) in enumerate(zip(columns, columns[1:])):
                if left - 0.5 <= word["x0"] < right - 0.5:
                    cells[i].append(word)
                    break
        row = [" ".join(w["text"] for w in sorted(cell, key=lambda w: (round(w["top"], 1), w["x0"]))) for cell in cells]
        if any(row):
            yield row


def parse_interprovincial_pdf(pdf, filename):
    rows = []
    columns = None
    for page in pdf.pages:
        headers = []
        for table in page.find_tables():
            extracted = table.extract(x_tolerance=1, y_tolerance=2)
            if extracted and header_mapping(extracted[0]):
                headers.append((table, extracted))
        headers.sort(key=lambda item: item[0].bbox[1])
        segments = []
        if columns:
            segments.append((0, headers[0][0].bbox[1] if headers else page.height, columns, None))
        for i, (table, extracted) in enumerate(headers):
            cells = table.rows[0].cells
            columns = [cell[0] for cell in cells if cell] + [cells[-1][2]]
            end = headers[i + 1][0].bbox[1] if i + 1 < len(headers) else page.height
            segments.append((table.rows[0].bbox[3], end, columns, extracted[0]))
        for top, bottom, bounds, header in segments:
            if header:
                rows.append(header)
            for row in _bands(page, top, bottom, bounds):
                if not text(row[0]) and not text(row[1]) and any(row[2:]):
                    if not rows or header_mapping(rows[-1]) or not text(rows[-1][1]):
                        raise ValueError("An interprovincial row continuation could not be linked to an athlete.")
                    rows[-1] = [text(f"{old or ''} {new or ''}") for old, new in zip(rows[-1], row)]
                else:
                    rows.append(row)
    event = recognize_metadata((pdf.pages[0].extract_text() or "").splitlines()[:4], filename, INTERPROVINCIAL)
    return normalize_rows(event, rows, league=False)
