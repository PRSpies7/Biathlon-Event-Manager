from __future__ import annotations

from typing import Any
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring


def build_results_xml(athletes: list[dict[str, Any]]) -> bytes:
    root = Element("results", {"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"})
    for a in athletes:
        if not a.get("run_time") or not a.get("swim_time"):
            continue
        result = SubElement(root, "result")
        SubElement(result, "athleteNo").text = str(a["athlete_number"])
        SubElement(result, "athleteName").text = str(a["athlete_name"])
        SubElement(result, "runtime").text = str(a["run_time"])
        SubElement(result, "swimtime").text = str(a["swim_time"])

    raw = tostring(root, encoding="utf-8")
    pretty = minidom.parseString(raw).toprettyxml(indent="\t", encoding="UTF-8")
    # minidom returns a bytes declaration but may use single quotes for standalone only if added manually.
    text = pretty.decode("utf-8")
    lines = text.splitlines()
    if lines and lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    else:
        lines.insert(0, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
    return ("\n".join(lines) + "\n").encode("utf-8")
