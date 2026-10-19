from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_quick_tools_opens_without_event_setup():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.session_state["app_module"] = "Quick Tools"
    app.run()
    assert not app.exception
    assert app.header[0].value == "Quick Tools"
    assert app.session_state["event_id"] is None
    assert len(app.get("file_uploader")) == 1


def test_uploaded_results_offer_xml_download():
    app = AppTest.from_string('''
from unittest.mock import patch
from exporters.master_excel import build_master_import_xlsx
from ui.quick_tools import render
upload = build_master_import_xlsx([
    {"athlete_number": "001", "athlete_name": "Edited Name", "run_time": "04:12.50", "swim_time": "01:03.25"}
])
upload.name = "Final Results edited.xlsx"
with patch("ui.quick_tools.st.file_uploader", return_value=upload):
    render()
''').run()
    assert not app.exception
    assert app.success[0].value == "XML ready: 1 athlete result(s)."
    assert len(app.get("download_button")) == 1


def test_invalid_upload_blocks_download():
    app = AppTest.from_string('''
from io import BytesIO
from unittest.mock import patch
from ui.quick_tools import render
upload = BytesIO(b"invalid workbook")
upload.name = "Invalid.xlsx"
with patch("ui.quick_tools.st.file_uploader", return_value=upload):
    render()
''').run()
    assert not app.exception
    assert "valid .xlsx" in app.error[0].value
    assert len(app.get("download_button")) == 0
