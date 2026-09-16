"""Focused tests: scanned routing, row isolation, and unconfirmed image previews."""
from io import BytesIO
from unittest.mock import patch
from PIL import Image
import pytest

from services.local_results_ocr import locate_rows
from services.results_verification import ManualReading, VerificationResult, verify_results, manual_value
from parsers.manual_results_pdf import extract_manual_pdf


def word(text, x, y):
    return dict(text=text, cx=x, cy=y, height=14, slope=0)


@pytest.mark.parametrize('discipline,id_x,name_x', [('run', 90, 250), ('swim', 170, 330)])
def test_athlete_row_locations_exclude_other_numbers(discipline, id_x, name_x):
    words = [word('1001', id_x, 300), word('John Smith', name_x, 300),
             word('01:30.00', 820, 300), word('2', id_x, 200),
             word('2027', id_x, 1350), word('Season', name_x, 1350)]
    rows = locate_rows(words, 1000, 1400, discipline)
    assert len(rows) == 1 and rows[0][0:2] == ('1001', 'John Smith')
    assert rows[0][2][0] >= 750


def test_scanned_parser_uses_local_backend_and_preserves_preview():
    from reportlab.pdfgen.canvas import Canvas
    pdf = BytesIO()
    canvas = Canvas(pdf)
    canvas.rect(10, 10, 20, 20)
    canvas.showPage()
    canvas.save()
    picture = BytesIO()
    Image.new('RGB', (20, 10), 'white').save(picture, format='PNG')
    reading = ManualReading('1001', 'John Smith', 'run', '01:00.00', False, 'Page 1', picture.getvalue())
    with patch('services.local_results_ocr.extract_scanned_page', return_value=([reading], ['Check original'])) as backend:
        rows, warnings = extract_manual_pdf(pdf.getvalue(), 'run', recognize_scans=True)
    backend.assert_called_once()
    assert rows == [reading] and warnings == ['Check original']
    issues = verify_results([VerificationResult('1001', 'John Smith', '01:00.00', swim_expected=False)], rows)
    assert len(issues) == 1 and issues[0].status == 'UNCERTAIN_RECOGNITION'
    assert issues[0].preview == picture.getvalue()


@pytest.mark.parametrize('raw,proposed', [('40:12', '00:40.12'), ('59,57', '00:59.57'), ('109,44', '1:09.44')])
def test_handwritten_separators_are_reviewable(raw, proposed):
    assert manual_value(raw) == (proposed, True)


def test_blank_time_box_is_not_sent_to_handwriting_model():
    from services.local_results_ocr import recognize_times
    with patch('services.local_results_ocr.printed_engine') as load:
        assert recognize_times([Image.new('RGB', (160, 40), 'white')]) == ['']
        load.assert_not_called()


@pytest.mark.parametrize('raw,proposed', [('10944', '1:09.44'), ('12203', '1:22.03'), ('1.1708', '1:17.08')])
def test_ocr_missing_separators_require_review(raw, proposed):
    assert manual_value(raw) == (proposed, True)
