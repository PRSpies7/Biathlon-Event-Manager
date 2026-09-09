"""Reports for the season database; no SQL or result scoring in the UI."""
from io import BytesIO

import streamlit as st
import pandas as pd

from database.season_repository import replace_record_benchmarks
from exporters.season_results import build_report_xlsx, build_season_results_xlsx, build_qualified_athletes_xlsx, build_qualified_schools_xlsx, build_top_athletes_xlsx, with_insights
from exporters.season_records import updated_records_xlsx
from services.school_reports import qualified_schools_report
from parsers.season_records import RECORD_HEADERS, category_key, record_category_key, parse_record_benchmarks
from services.season_reports import (
    RECORD_REPORT_HEADERS, age_group_sort_key, filtered_snapshot, qualified_report_rows,
    record_comparison_rows, school_snapshot,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _records(db_path, snapshot):
    st.subheader("Records", help="Only age group and record points are required. Equivalent age-group wording is matched while ages and sexes remain separate. Preview immediately compares published total points with the references; save to retain them. Equal and higher scores appear in the comparison. The updated workbook preserves the supplied layout, SA-record values and formulas; strictly higher scores replace holders, while equal scores remain in the comparison report.")
    if snapshot.get("record_templates"):
        try:
            st.download_button("Download updated records list (.xlsx)", data=updated_records_xlsx(snapshot),
                file_name="Gauteng North Biathlon Records - Updated.xlsx", mime=XLSX_MIME, key="season_updated_records", type="primary")
        except ValueError as exc:
            st.info(str(exc))
    with st.expander("Supply current records", expanded=not bool(snapshot.get("records"))):
        categories = sorted({category_key(r["category"]): r["category"] for r in snapshot["results"]}.values(), key=age_group_sort_key)
        template = [{"Category": c} for c in categories] or [{"Category": ""}]
        st.download_button("Download current records template (.xlsx)",
            data=build_report_xlsx("Current Records", RECORD_HEADERS, template),
            file_name="Current Records Template.xlsx", mime=XLSX_MIME, key="season_records_template")
        st.caption("Upload your existing GN records workbook directly. Only age group and record points are required; athlete number and name are optional.")
        upload = st.file_uploader("Current records (.xlsx)", type=["xlsx"], key="season_records_upload")
        if st.button("Preview current records", key="season_records_preview_button", disabled=upload is None):
            st.session_state.pop("season_records_preview", None)
            try:
                records = parse_record_benchmarks(BytesIO(upload.getvalue()))
                names = {a["athlete_number"]: a["athlete_name"] for a in snapshot["athletes"]}
                for record in records:
                    record["athlete_name"] = record["athlete_name"] or names.get(record["athlete_number"], "")
                st.session_state.season_records_preview = {"records": records, "source": upload.name, "template_bytes": upload.getvalue()}
            except Exception as exc:
                st.error(f"Could not read current records: {exc}")
        preview = st.session_state.get("season_records_preview")
        if preview:
            st.write(f"{preview['source']}: {len(preview['records'])} category records")
            st.dataframe([{h: r[h.lower().replace(' ', '_')] for h in RECORD_HEADERS} for r in preview["records"]], hide_index=True)
            st.caption("Saving replaces the complete saved current-records list. Published event results stay as imported.")
            if st.button("Save current records", type="primary", key="season_records_save"):
                replace_record_benchmarks(db_path, preview["records"], preview["source"], preview.get("template_bytes"))
                st.session_state.pop("season_records_preview", None)
                st.session_state.season_records_saved = True
                st.rerun()
    if st.session_state.pop("season_records_saved", False):
        st.success("Current records saved.")
    if preview:
        snapshot = {**snapshot, "records": preview["records"]}
        st.info("Preview comparison below. Select Save current records to keep these references and enable the updated records-list download.")
    if not snapshot.get("records"):
        st.info("Supply current category records to enable the Records report.")
        return
    st.caption(f"{len(snapshot['records'])} category records {'in preview' if preview else 'saved'}.")
    covered = {record_category_key(r["category"]) for r in snapshot["records"]}
    missing = sorted({r["category"] for r in snapshot["results"] if record_category_key(r["category"]) not in covered})
    if missing:
        st.info("No record supplied for: " + "; ".join(missing))
    rows = record_comparison_rows(snapshot)
    if rows:
        st.dataframe(rows, hide_index=True)
    else:
        st.info("No published total points exceed or equal the supplied records in matching age groups.")
    st.download_button("Download records report (.xlsx)",
        data=build_report_xlsx("Records", RECORD_REPORT_HEADERS, rows),
        file_name="Records Report.xlsx", mime=XLSX_MIME, key="season_records_download", type="primary")


def render(db_path, snapshot):
    st.subheader("Full database", help="All season athletes, published event results, events and awards, plus saved record references. Athlete summaries show their best result in their latest age group; event rows retain the published data.")
    st.download_button("Download full database (.xlsx)", data=build_season_results_xlsx(snapshot),
        file_name="Season Results Database.xlsx", mime=XLSX_MIME, disabled=not (snapshot["events"] or snapshot.get("records")),
        type="primary", key="season_download")
    st.divider()
    st.subheader("Primary schools and high schools results", help="All athletes with a known school, including affiliation and their results at every event. Results are ordered by age group, then total points.")
    schools = school_snapshot(snapshot)
    st.download_button("Download school results (.xlsx)", data=build_season_results_xlsx(schools),
        file_name="Primary and High Schools Results.xlsx", mime=XLSX_MIME, disabled=not schools["athletes"],
        type="primary", key="season_schools_download")
    st.divider()
    st.subheader("Qualified schools", help="Ps identifies primary schools; Hs identifies high schools. Schools rank by their selected team's season total. Primary: U9, U11, U13, U15 plus two extras. High: U15, U17, U19 plus three extras. Mandatory groups must be filled before extras count. Qualified replacements take priority; boys and girls share places. At most one special-needs athlete can fill an extra place, capped at 2,000 points. Each selected athlete needs four distinct completed meets including an interprovincial or GN Championship, and a best score of at least 1,890. The athlete sheet shows every event score and missing requirements. School names and qualification cells are highlighted.")
    summary, school_headers, school_athletes = qualified_schools_report(snapshot)
    st.download_button("Download qualified schools (.xlsx)",
        data=build_qualified_schools_xlsx(summary, school_headers, school_athletes),
        file_name="Qualified Schools - Full Season.xlsx", mime=XLSX_MIME, disabled=not summary,
        type="primary", key="season_qualified_schools_download")
    if summary:
        with st.expander("Preview school qualification"):
            st.dataframe(pd.DataFrame(summary).style.apply(lambda row: qualification_colours(row, "School"), axis=1), hide_index=True)
    st.divider()
    st.subheader("Affiliated athletes", help="Currently affiliated athletes with school, age group, attendance and event details; no points. The second sheet, Insights, lists and counts all season athletes who attended two or more events but have not affiliated, for payment follow-up.")
    affiliated = filtered_snapshot(snapshot, {a["athlete_number"] for a in snapshot["athletes"] if a["affiliated"]})
    st.download_button("Download affiliated athletes (.xlsx)",
        data=with_insights(build_season_results_xlsx(affiliated, include_points=False), snapshot, affiliation_only=True),
        file_name="Affiliated Athletes.xlsx", mime=XLSX_MIME, disabled=not snapshot["athletes"],
        type="primary", key="season_affiliated_download")
    st.divider()
    st.subheader("Qualified athletes", help="All athletes ranked by age group and highest total, with attendance count, Yes/No qualification and missing requirements. Only the highest total score is shown, without per-event scores or run/swim detail. Names and qualification cells are green/red. Top Athletes provides the event details. Four distinct completed meets are required (three for juniors, seniors and masters), including at least one interprovincial or GN Championship. Best completed score in the latest category must reach 1,890 (1,790 for juniors, seniors and masters), including the accepted 10-point allowance. Insights highlights participation, small age groups, strong one-event performers and affiliation follow-up.")
    qualified = qualified_report_rows(snapshot)
    st.download_button("Download qualified athletes (.xlsx)", data=build_qualified_athletes_xlsx(snapshot, qualified),
        file_name="Qualified Athletes.xlsx", mime=XLSX_MIME, disabled=not snapshot["athletes"],
        type="primary", key="season_qualified_download")
    if qualified:
        with st.expander("Preview athlete qualification"):
            st.dataframe(pd.DataFrame(qualified).style.apply(lambda row: qualification_colours(row, "Athlete name"), axis=1), hide_index=True)
    st.divider()
    st.subheader("Top athletes", help="All athletes ranked within age group by their highest single-event total. The main sheet shows affiliation, school and every event total; Event Details includes run/swim times, running/swimming points, bonus and total for each event. Insights is the second sheet, with participation charts and follow-up lists. This is a performance report and does not filter on qualification.")
    st.download_button("Download top athletes (.xlsx)", data=build_top_athletes_xlsx(snapshot),
        file_name="Top Athletes - Full Season.xlsx", mime=XLSX_MIME, disabled=not snapshot["results"],
        type="primary", key="season_top_athletes_download")
    st.divider()
    _records(db_path, snapshot)


def qualification_colours(row, name_column):
    colour = "background-color: #c6efce; color: #006100" if row["Qualified"] == "Yes" else "background-color: #ffc7ce; color: #9c0006"
    return [colour if column in {name_column, "Qualified"} else "" for column in row.index]
