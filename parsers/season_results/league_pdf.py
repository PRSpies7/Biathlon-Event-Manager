"""League reports have ruled tables, including wrapped names and school cells."""
from __future__ import annotations

from .common import header_mapping, normalize_rows, recognize_metadata
from .models import LEAGUE


def parse_league_pdf(pdf, filename):
    rows = []
    for page in pdf.pages:
        for table in sorted(page.find_tables(), key=lambda t: t.bbox[1]):
            extracted = table.extract(x_tolerance=1, y_tolerance=2)
            # Ignore the full-page decorative frame, which also looks like a table.
            if extracted and header_mapping(extracted[0]):
                rows.extend(extracted)
    event = recognize_metadata((pdf.pages[0].extract_text() or "").splitlines()[:5], filename, LEAGUE)
    return normalize_rows(event, rows, league=True)
