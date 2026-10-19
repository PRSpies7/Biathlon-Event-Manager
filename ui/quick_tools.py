from pathlib import Path

import streamlit as st

from exporters.results_xml import build_results_xml
from parsers.final_results_excel import parse_final_results_excel


def render():
    st.header("Quick Tools")
    st.subheader("Final Results: Excel to XML")
    st.caption("Upload an edited final-results Excel export and download the matching XML. No event setup is needed, and saved event results are unchanged.")
    upload = st.file_uploader("Upload final results Excel", type=["xlsx"], key="quick_results_excel")
    st.caption("Keep the original columns: Athlete nr, Athlete Name, athleteSurname, runtime and swimtime. Use times such as 04:12.50; blank or 00:00.00 means no result.")
    if upload is None:
        return
    try:
        athletes = parse_final_results_excel(upload)
        xml = build_results_xml(athletes)
    except ValueError as exc:
        st.error(str(exc))
        return
    exportable = [a for a in athletes if a.get("run_time") or a.get("swim_time")]
    partial = sum(not (a.get("run_time") and a.get("swim_time")) for a in exportable)
    st.success(f"XML ready: {len(exportable)} athlete result(s).")
    if partial:
        st.info(f"{partial} athlete(s) have partial results. Missing times export as 00:00.00.")
    if len(exportable) < len(athletes):
        st.caption(f"{len(athletes) - len(exportable)} athlete(s) with no results are excluded.")
    st.download_button("Download Final Results XML", data=xml,
                       file_name=f"{Path(upload.name).stem}.xml", mime="application/xml",
                       type="primary", key="quick_results_xml_download")
