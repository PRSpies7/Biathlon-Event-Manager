"""Reports for the season database; no SQL or result scoring in the UI."""
from io import BytesIO

import streamlit as st

from database.season_repository import replace_record_benchmarks
from exporters.season_results import build_report_xlsx, build_season_results_xlsx
from exporters.season_records import updated_records_xlsx
from exporters.season_combined import report_date
from parsers.season_records import RECORD_HEADERS, category_key, record_category_key, parse_record_benchmarks
from services.season_reports import (
    RECORD_REPORT_HEADERS, age_group_sort_key, record_comparison_rows,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _records(db_path, snapshot):
    st.subheader("Records", help="Only age group and record points are required. Equivalent age-group wording is matched while ages and sexes remain separate. Preview immediately compares published total points with the references; save to retain them. Equal and higher scores appear in the comparison. The updated workbook preserves the supplied layout, SA-record values and formulas; strictly higher scores replace holders, while equal scores remain in the comparison report.")
    if snapshot.get("record_templates"):
        try:
            st.download_button("Download updated records list (.xlsx)", data=updated_records_xlsx(snapshot),
                file_name=f"Gauteng North Biathlon Records - Updated - {report_date()}.xlsx", mime=XLSX_MIME, key="season_updated_records", type="primary")
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
    from exporters.selection_reports import _tidy
    from exporters.season_combined import report_date
    st.download_button("Download records report (.xlsx)",
        data=_tidy(build_report_xlsx("Records", RECORD_REPORT_HEADERS, rows)),
        file_name=f"Records Report - {report_date()}.xlsx", mime=XLSX_MIME, key="season_records_download", type="primary")


def render(db_path, snapshot):
    from exporters.season_combined import build_combined_season_xlsx, report_date
    st.subheader("Season qualification and results")
    if snapshot.get("season_year") == 2027:
        st.caption("2027 attendance: U/08–U/19 need 4 completed events; JNR through Masters 80+ need 3. Each needs at least one interprovincial or GN Championship; additional IP/championship events can substitute for leagues. Each event counts once. Summary separates Qualification Status from Qualification requirements.")
    st.caption("One workbook: Summary, All Results, Primary Schools and High Schools. Runner/swimmer columns show published award placings. Victor/victrix uses the highest completed total at each event, split by sex and junior (U/08–U/19) or senior; special needs categories are excluded. Ties share the award.")
    st.download_button("Download season report (.xlsx)", data=build_combined_season_xlsx(snapshot),
        file_name=f"GN Season Report - {snapshot.get('season_year') or 'Selected Season'} - {report_date().isoformat()}.xlsx",
        mime=XLSX_MIME, disabled=not snapshot["results"], type="primary", key="season_combined_download")
    with st.expander("Specialist selection reports"):
        _specialist_reports(db_path, snapshot)
    with st.expander("Records"):
        _records(db_path, snapshot)


def _specialist_reports(db_path, snapshot):
    from exporters.selection_reports import (build_athlete_selection_xlsx, build_school_selection_xlsx,
        build_ranked_athletes_xlsx, build_affiliation_xlsx, _tidy)
    from exporters.season_combined import report_date
    stamp = f"{snapshot.get('season_year') or 'Unassigned'} - {report_date()}"
    reports = [
        ("Athlete qualification", "For team selection: category rank, best score, qualification status and outstanding requirements. One tab, including athletes who still need events or points.",
         "season_qualified_download", "Download athlete qualification (.xlsx)", build_athlete_selection_xlsx),
        ("School qualification and teams", "Primary Schools then High Schools. Team athletes and Highest scores identify the selected scoring team. All school athletes lists every athlete with a completed season result, their age group and highest completed score; DNF-only athletes are excluded. Missing events and requirements refer to team positions. Each selected athlete contributes once. School types need Ps or Hs in the name.",
         "season_qualified_schools_download", "Download school qualification (.xlsx)", build_school_selection_xlsx),
        ("Ranked athletes", "Ranked Athletes first for comparing performances, followed by Event Details for checking individual times and scores. Qualification is a separate report.",
         "season_top_athletes_download", "Download ranked athletes (.xlsx)", build_ranked_athletes_xlsx),
        ("Affiliation and follow-up", "Affiliated Athletes first; Affiliation Follow-up lists athletes who attended at least two events and are not affiliated. No repeated event-result or award tabs.",
         "season_affiliated_download", "Download affiliation report (.xlsx)", build_affiliation_xlsx),
    ]
    for title,description,key,label,builder in reports:
        with st.container(border=True):
            st.subheader(title)
            st.caption(description)
            st.download_button(label,data=builder(snapshot),file_name=f"{title} - {stamp}.xlsx",
                mime=XLSX_MIME,key=key,disabled=not snapshot["athletes"])
    with st.expander("Full database export"):
        st.caption("For archival or detailed data checks. This includes the underlying athletes, event results, imported events, awards and saved records; use the focused reports above for selection.")
        st.download_button("Download full database (.xlsx)",data=_tidy(build_season_results_xlsx(snapshot)),
            file_name=f"Season Database - {stamp}.xlsx",mime=XLSX_MIME,key="season_download",
            disabled=not (snapshot["events"] or snapshot.get("records")))


def qualification_colours(row, name_column):
    colour = "background-color: #c6efce; color: #006100" if row["Qualified"] == "Yes" else "background-color: #ffc7ce; color: #9c0006"
    return [colour if column in {name_column, "Qualified"} else "" for column in row.index]
