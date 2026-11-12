"""Purpose-specific selection workbooks with one authoritative view per tab."""
from io import BytesIO
import textwrap

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from exporters.season_results import _build_workbook, build_season_results_xlsx
from exporters.season_combined import report_date
from services.season_reports import qualified_athlete_report, top_athlete_report, compact_qualification_requirements
from services.school_reports import qualified_schools_report
from services.season_insights import insight_sections


def _dataset(title, headers, rows):
    return title,headers,[[compact_qualification_requirements(r.get(h,"")) if h == "Missing to qualify"
                           else r.get(h, "") for h in headers] for r in rows]


def build_athlete_selection_xlsx(snapshot):
    headers,rows = qualified_athlete_report(snapshot)
    # Includes everyone, so selectors can filter qualified athletes or outstanding needs.
    return _tidy(_build_workbook([_dataset("Athlete Qualification",headers,rows)]))


def build_school_selection_xlsx(snapshot):
    summary,detail_headers,details = qualified_schools_report(snapshot)
    headers = ["Rank","School","Total school points","Qualified","Full team",
               "Missing team members","Missing Events","Qualification requirements","Team athletes","Highest scores","All school athletes"]
    datasets = []
    for kind,title in (("Primary","Primary Schools"),("High","High Schools")):
        rows = [dict(r) for r in summary if r["School type"] == kind]
        previous,rank = None,0
        for i,row in enumerate(rows,1):
            if row["Total school points"] != previous:
                rank = i
            previous = row["Total school points"]
            row["Rank"] = rank
        datasets.append(_dataset(title,headers,rows))
    # Detail supports checking team places and replacements; no duplicate combined summary.
    datasets.append(_dataset("School Athlete Scores",detail_headers,details))
    return _tidy(_build_workbook(datasets))


def build_ranked_athletes_xlsx(snapshot):
    headers,rows = top_athlete_report(snapshot)
    book = load_workbook(_build_workbook([_dataset("Ranked Athletes",headers,rows)]))
    source = load_workbook(build_season_results_xlsx(snapshot))["Event Results"]
    detail = book.create_sheet("Event Details")
    # Omit internal database IDs; event and athlete identities remain visible.
    keep = [c.column for c in source[1] if c.value != "Event id"]
    for row in source:
        detail.append([row[i-1].value for i in keep])
    return _tidy(book)


def build_affiliation_xlsx(snapshot):
    headers = ["Athlete number","Athlete name","School","Age group","Affiliated","Events attended"]
    from services.season_reports import athlete_result_rows
    rows = [r for r in athlete_result_rows(snapshot) if r["Affiliated"] == "Affiliated"]
    _,follow_headers,follow_rows = insight_sections(snapshot,affiliation_only=True)[0]
    return _tidy(_build_workbook([_dataset("Affiliated Athletes",headers,rows),
                                 _dataset("Affiliation Follow-up",follow_headers,follow_rows)]))


def _tidy(source):
    book = load_workbook(source) if not hasattr(source,"worksheets") else source
    for sheet in book:
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "C2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 44
        widths = []
        for cell in sheet[1]:
            label = str(cell.value)
            label_lower = label.lower()
            width = (72 if label_lower == "all school athletes" else 50 if label_lower == "team athletes" else 36 if label_lower == "highest scores" else 58 if any(t in label_lower for t in ("missing","requirements")) else
                     28 if any(t in label_lower for t in ("name","school","event")) else 20)
            if label_lower == "all school athletes":
                width = max(72,min(144,max((len(line)+2 for row in sheet.iter_rows(min_row=2)
                                          for line in str(row[cell.column-1].value or "").split("\n")),default=72)))
            widths.append(width)
            sheet.column_dimensions[cell.column_letter].width = width
            cell.font = Font(name="Calibri",size=11,bold=True,color="FFFFFF")
            cell.fill = PatternFill("solid",fgColor="1F4E78")
            cell.alignment = Alignment(wrap_text=True,vertical="center")
        for row in sheet.iter_rows(min_row=2):
            for c in row:
                label = str(sheet.cell(1,c.column).value).lower()
                c.font = Font(name="Calibri",size=11,color="243746")
                c.fill = PatternFill("solid",fgColor="F2F6FA" if c.row%2 else "FFFFFF")
                c.border = Border(bottom=Side(style="thin",color="D8E2EC"))
                c.alignment = Alignment(vertical="center",wrap_text=True)
                if isinstance(c.value,str):
                    c.data_type = "s"
                if isinstance(c.value,(int,float)):
                    c.number_format = "#,##0.00" if "points" in label else "0"
                if label in {"qualified","full team","selected"}:
                    c.fill = PatternFill("solid",fgColor="C6EFCE" if c.value == "Yes" else "FFC7CE")
                    c.font = Font(name="Calibri",size=11,bold=True,color="006100" if c.value == "Yes" else "9C0006")
            lines = max((sum(max(1,len(textwrap.wrap(part,width=int(widths[c.column-1]))))
                             for part in str(c.value or "").split("\n")) for c in row),default=1)
            sheet.row_dimensions[row[0].row].height = max(28,lines*15+8)
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = "1:1"
        sheet.oddFooter.center.text = f"Generated {report_date()} · Page &P of &N"
    output = BytesIO()
    book.save(output)
    output.seek(0)
    return output
