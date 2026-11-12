"""Combined season report following the supplied Summary / All Results layout."""
from collections import defaultdict
from datetime import datetime
from io import BytesIO
import re
import textwrap
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from services.season_reports import (top_athlete_report, qualification_rows,
    attendance_qualification, age_group_sort_key, numeric_points, completed_result,
    compact_qualification_requirements)
from services.school_reports import qualified_schools_report
from exporters.season_results import _build_workbook


def report_date():
    return datetime.now(ZoneInfo("Africa/Johannesburg")).date()


def _event_key(event):
    match = re.search(r"league\s*(\d+)", event["name"], re.I)
    return (0, int(match[1]), event["event_date"], event["id"]) if match else (1, 0, event["event_date"], event["id"])


def _position(result):
    value = str(result.get("position") or "").strip()
    return int(value) if value.isdigit() else None


def build_combined_season_xlsx(snapshot):
    events = sorted(snapshot["events"], key=_event_key)
    labels = {e["id"]: f"{e['name']}\n{e['event_date']}" for e in events}
    top_headers, top = top_athlete_report(snapshot)
    old_labels = {e["id"]: label for e,label in zip(sorted(snapshot["events"],key=lambda e:(e["event_date"],e["id"])),top_headers[10:])}
    qualifications = {r["Athlete number"]:r for r in qualification_rows(snapshot)}
    by_athlete = defaultdict(list)
    for r in snapshot["results"]:
        by_athlete[r["athlete_number"]].append(r)
    summary_headers = ["Category","Athlete #","Athlete","School","AFL",*labels.values(),
                       "Leagues Count","IP / Champs Count","Best Points","Pos in Category","Qualification Status","Qualification requirements"]
    summary = []
    for row in top:
        attendance = attendance_qualification(by_athlete[row["Athlete number"]])
        q = qualifications[row["Athlete number"]]
        summary.append([row["Age group"],row["Athlete number"],row["Athlete name"],row["School"],
                        "Yes" if row["Affiliated"] == "Affiliated" else "No",
                        *[row.get(old_labels[e["id"]],"") for e in events],
                        attendance["Completed league events"],
                        attendance["Completed interprovincial events"] + attendance["Completed championship events"],
                        row["Highest total points"],row["Rank"],
                        "Qualified" if q["Qualified"] == "Yes" else "Not qualified",
                        "None" if q["Qualified"] == "Yes" else compact_qualification_requirements(q["Missing to qualify"])])

    # Victor/victrix: best completed total per event, sex and junior/senior band.
    contenders = defaultdict(list)
    for r in snapshot["results"]:
        category = r["category"].upper()
        if "SPECIAL" in category or not completed_result(r):
            continue
        sex = "Female" if re.search(r"GIRLS?|WOMEN|FEMALE|LADIES",category) else "Male" if re.search(r"BOYS?|MEN|MALE",category) else None
        age = re.search(r"(?:U\s*/?\s*|UNDER[ -]*)(\d+)",category)
        band = "Junior" if age and 8 <= int(age[1]) <= 19 else "Senior"
        points = numeric_points(r["total_points"])
        if sex and points is not None:
            contenders[(r["event_id"],band,sex)].append((points,r["athlete_id"]))
    victors = defaultdict(list)
    for (event,band,sex), candidates in contenders.items():
        best = max(p for p,_ in candidates)
        for points,athlete in candidates:
            if points == best:
                victors[(event,athlete)].append(f"{band} {'Victrix' if sex == 'Female' else 'Victor'}")
    awards = defaultdict(list)
    for a in snapshot["awards"]:
        awards[(a["event_id"],a["athlete_id"],a["award_type"])].append(str(a["placing"]))
    athletes = {a["id"]:a for a in snapshot["athletes"]}
    order = {e["id"]:i for i,e in enumerate(events)}
    headers = ["Event","Date","Category","Pos","Athlete #","Athlete","School","AFL","Run Time","Run Pts",
               "Swim Time","Swim Pts","Bonus","Total","PB","Top runner placing","Top swimmer placing","Victor / Victrix"]
    results = []
    for r in sorted(snapshot["results"],key=lambda r:(order[r["event_id"]],age_group_sort_key(r["category"]),_position(r) or 99999)):
        key = (r["event_id"],r["athlete_id"])
        results.append([r["event_name"],r["event_date"],r["category"],_position(r),r["athlete_number"],r["athlete_name"],r["school"],
                        "Yes" if athletes[r["athlete_id"]]["affiliated"] else "No",r["run_time"],r["running_points"],r["swim_time"],
                        r["swimming_points"],r["bonus_points"],r["total_points"],"PB" if re.search(r"\bPB\b",r.get("annotations") or "") else "",
                        ", ".join(awards[(*key,"Runner")]),", ".join(awards[(*key,"Swimmer")]),", ".join(victors[key])])
    school_summary,_,_ = qualified_schools_report(snapshot)
    school_headers = ["Rank","School","Total school points","Qualified","Full team","Missing team members","Missing Events","Qualification requirements","Team athletes","Highest scores","All school athletes"]
    datasets = [("Summary",summary_headers,summary),("All Results",headers,results)]
    for kind,title in (("Primary","Primary Schools"),("High","High Schools")):
        schools = [r for r in school_summary if r["School type"] == kind]
        last,rank = None,0
        rows = []
        for i,r in enumerate(schools,1):
            if r["Total school points"] != last:
                rank = i
            last = r["Total school points"]
            rows.append([rank,*[r.get(h,"") for h in school_headers[1:]]])
        datasets.append((title,school_headers,rows))
    workbook = load_workbook(_build_workbook(datasets))
    sheet = workbook["Summary"]
    sheet.insert_rows(1,2)
    sheet.cell(1,1,f"GN League & Championships — Combined Total Points · {report_date().isoformat()}")
    sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(summary_headers))
    sheet.cell(1,1).font = Font(size=16,bold=True,color="1F4E78")
    _format_report(workbook, len(events))
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _format_report(workbook, event_count):
    """Contiguous filter ranges; compact reference-style typography and spacing."""
    navy, pale, ink = "1F4E78", "F2F6FA", "243746"
    rule = Side(style="thin", color="D8E2EC")
    group_rule = Side(style="medium", color="9DB5CD")
    for sheet in workbook:
        summary = sheet.title == "Summary"
        header = 3 if summary else 1
        sheet.sheet_view.showGridLines = False
        sheet.sheet_view.zoomScale = 85 if summary else 90
        sheet.sheet_properties.tabColor = navy
        sheet.sheet_format.defaultRowHeight = 20
        sheet.freeze_panes = "F4" if summary else "F2" if sheet.title == "All Results" else "C2"
        sheet.auto_filter.ref = f"A{header}:{get_column_letter(sheet.max_column)}{max(header,sheet.max_row)}"
        # No merged category bands or blank separator rows inside filterable data.
        if summary:
            widths = [18,11,27,26,7] + [15] * event_count + [11,13,13,11,19,48]
            sheet.row_dimensions[1].height = 28
            sheet.row_dimensions[2].height = 9
        elif sheet.title == "All Results":
            widths = [17,12,21,7,11,27,26,7,12,11,12,11,9,12,7,17,17,23]
        else:
            widths = [8,29,16,13,13,32,42,48,50,36,72]
            widths[-1] = max(72,min(144,max((len(line)+2 for row in sheet.iter_rows(min_row=2)
                                           for line in str(row[-1].value or "").split("\n")),default=72)))
        for i,width in enumerate(widths,1):
            sheet.column_dimensions[get_column_letter(i)].width = width
        sheet.row_dimensions[header].height = 42 if summary else 32
        for cell in sheet[header]:
            cell.font = Font(name="Calibri",size=11,bold=True,color="FFFFFF")
            cell.fill = PatternFill("solid",fgColor=navy)
            cell.alignment = Alignment(horizontal="center",vertical="center",wrap_text=True)
            cell.border = Border(bottom=rule)
        previous_category = None
        for row in sheet.iter_rows(min_row=header+1):
            category = row[0].value if summary else None
            new_group = summary and category != previous_category
            previous_category = category
            fill = PatternFill("solid",fgColor="FFFFFF" if (row[0].row-header)%2 else pale)
            for cell in row:
                cell.font = Font(name="Calibri",size=11,color=ink)
                cell.fill = fill
                label = str(sheet.cell(header,cell.column).value)
                numeric = isinstance(cell.value,(int,float))
                centred = label.casefold() in {"category","athlete #","afl","pos","pb","rank","qualified","qualification status","full team","leagues count","ip / champs count","pos in category","top runner placing","top swimmer placing"}
                cell.alignment = Alignment(horizontal="center" if centred else "right" if numeric else "left",vertical="center",wrap_text=True)
                cell.border = Border(bottom=rule,top=group_rule if new_group else Side())
                if summary and (5 < cell.column <= 5+event_count or label == "Best Points"):
                    cell.number_format = "#,##0.00"
                if sheet.title == "All Results" and cell.column in (10,12,13,14):
                    value = numeric_points(cell.value)
                    if value is not None:
                        cell.value = float(value)
                        cell.number_format = "#,##0.00"
                if "points" in label.lower() and numeric:
                    cell.number_format = "#,##0.00"
                if label.casefold() in {"qualification status","qualified","full team"} and cell.value:
                    yes = cell.value in {"Qualified","Yes"}
                    cell.fill = PatternFill("solid",fgColor="C6EFCE" if yes else "FFC7CE")
                    cell.font = Font(name="Calibri",size=11,color="006100" if yes else "9C0006",bold=True)
            if summary:
                # A fixed height prevents imported row dimensions from stretching
                # arbitrary athletes; the wide status field fits the qualification text.
                sheet.row_dimensions[row[0].row].height = 32
            elif sheet.title == "All Results":
                sheet.row_dimensions[row[0].row].height = 28
            else:
                lines = max((sum(max(1,len(textwrap.wrap(line,width=max(1,int(widths[c.column-1])))))
                                 for line in str(c.value or "").split("\n")) for c in row),default=1)
                sheet.row_dimensions[row[0].row].height = max(30,lines*15+8)
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = f"1:{header}"
        sheet.print_options.horizontalCentered = True
        sheet.print_area = f"A1:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        sheet.oddFooter.center.text = f"Generated {report_date().isoformat()} · Page &P of &N"
