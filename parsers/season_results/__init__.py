"""Adapters for finalized league/interprovincial results, separate from ingestion."""
from __future__ import annotations

from pathlib import Path
from collections import Counter
import re

import pdfplumber

from .excel import parse_excel
from .interprovincial_pdf import parse_interprovincial_pdf
from .league_pdf import parse_league_pdf
from .common import header_mapping
from .models import is_gn_championship


def parse_season_results(source, filename: str | None = None):
    filename = Path(filename or getattr(source, "name", str(source))).name
    suffix = Path(filename).suffix.casefold()
    if hasattr(source, "seek"):
        source.seek(0)
    if suffix == ".xlsx":
        return parse_excel(source, filename)
    if suffix == ".pdf":
        with pdfplumber.open(source) as pdf:
            if not pdf.pages:
                raise ValueError("This PDF has no pages.")
            first = pdf.pages[0].extract_text() or ""
            if not first.strip():
                raise ValueError("This PDF has no extractable text. Upload the original text PDF or Excel results.")
            if is_gn_championship(" ".join(first.splitlines()[:5])):
                # GN championships can use either supported published report layout.
                mappings = [header_mapping(t.extract()[0]) for t in pdf.pages[0].find_tables() if t.rows]
                team_layout = any(m and ("team" in m.values() or "province" in m.values()) for m in mappings)
                event = (parse_interprovincial_pdf if team_layout else parse_league_pdf)(pdf, filename)
            elif re.search(r"inter[ -]?provincial", first, re.I):
                event = parse_interprovincial_pdf(pdf, filename)
            elif re.search(r"league\s*\d+", first, re.I):
                event = parse_league_pdf(pdf, filename)
            else:
                raise ValueError("Unrecognized PDF layout. Version 1 supports league, interprovincial and Gauteng North Championship reports using the supported layouts.")
            # A separate text pass catches recognizable rows omitted by table extraction.
            # This checks extraction coverage only, never the published competition result.
            source_numbers = Counter(number for page in pdf.pages for number in
                re.findall(r"^\s*(?:\d+|DNF|DNS|DQ|DSQ)\s+(\d+)\s", page.extract_text() or "", re.M))
            parsed_numbers = Counter(r.athlete_number for r in event.results + event.awards)
            if source_numbers - parsed_numbers:
                raise ValueError("Some PDF result rows could not be extracted completely. Import stopped; use the Excel results or the original supported PDF layout.")
            if any("\ufffd" in r.athlete_name for r in event.results):
                event.notes.append("Some names contain unreadable characters in the PDF text. Prefer the Excel source if available.")
            return event
    raise ValueError("Upload a PDF or .xlsx finalized results file.")
