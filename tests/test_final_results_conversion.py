from datetime import time, timedelta
from io import BytesIO
import unittest
from xml.etree import ElementTree

from openpyxl import Workbook

from exporters.master_excel import build_master_import_xlsx
from exporters.results_xml import build_results_xml
from parsers.final_results_excel import parse_final_results_excel


class FinalResultsConversionTests(unittest.TestCase):
    def workbook(self, rows, headers=None):
        wb = Workbook()
        wb.active.title = "FOR IMPORT"
        wb.active.append(headers or ["Athlete nr", "Athlete Name", "athleteSurname", "runtime", "swimtime"])
        for row in rows:
            wb.active.append(row)
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    def test_export_round_trip_matches_existing_xml(self):
        athletes = [
            {"athlete_number": "00123", "athlete_name": "A & B", "run_time": "04:12.50", "swim_time": "01:03.25"},
            {"athlete_number": "456", "athlete_name": "Partial", "run_time": None, "swim_time": "00:42.00"},
        ]
        parsed = parse_final_results_excel(build_master_import_xlsx(athletes))
        self.assertEqual(build_results_xml(parsed), build_results_xml(athletes))

    def test_edits_surname_and_partial_results(self):
        source = self.workbook([
            [123, "New name", "Surname & Sons", "4;13.50", "00:00.00"],
            [456, "No results", "No results", None, None],
        ])
        root = ElementTree.fromstring(build_results_xml(parse_final_results_excel(source)))
        self.assertEqual(len(root), 1)
        self.assertEqual(root[0].findtext("athleteNo"), "123")
        self.assertEqual(root[0].findtext("athleteSurname"), "Surname & Sons")
        self.assertEqual(root[0].findtext("runtime"), "04:13.50")
        self.assertEqual(root[0].findtext("swimtime"), "00:00.00")

    def test_native_excel_times(self):
        parsed = parse_final_results_excel(self.workbook([
            ["001", "Name", "Name", time(0, 4, 12, 500000), timedelta(seconds=63.25)],
        ]))
        self.assertEqual(parsed[0]["run_time"], "04:12.50")
        self.assertEqual(parsed[0]["swim_time"], "01:03.25")

    def test_invalid_workbooks_block_conversion(self):
        cases = [
            ([[1, "Name", "Name", "04:61.00", "01:00.00"]], "Row 2, runtime"),
            ([[1, "Name", "Name", "04:00.00", None], [1, "Other", "Other", "04:01.00", None]], "Duplicate athlete numbers"),
            ([[None, "Name", "Name", "04:00.00", None]], "blank athlete number"),
            ([[1, None, None, "04:00.00", None]], "blank athlete name"),
            ([[1, "Name", "Name", '=TEXT(1,"mm:ss.00")', None]], "replace the formula"),
            ([[1, "Name", "Name", "#VALUE!", None]], "correct the Excel error"),
            ([[1, "Name", "Name", None, "00:00.00"]], "no results"),
        ]
        for rows, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_final_results_excel(self.workbook(rows))

    def test_missing_headers_and_invalid_file(self):
        with self.assertRaisesRegex(ValueError, "Missing columns"):
            parse_final_results_excel(self.workbook([], ["Wrong layout"]))
        with self.assertRaisesRegex(ValueError, "valid .xlsx"):
            parse_final_results_excel(BytesIO(b"not an Excel workbook"))


if __name__ == "__main__":
    unittest.main()
