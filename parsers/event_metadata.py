"""Optional metadata printed in the existing heat-document structure."""
import re


def read_metadata(lines):
    result={}
    names={"event":"meet_name","date":"start_date","season":"season_year","pool lanes":"pool_lanes",
           "run positions":"run_positions","meet type":"meet_type","course":"course","host":"host_team"}
    for line in lines:
        for part in str(line).split(" | "):
            match=re.match(r"^(Event|Date|Season|Pool lanes|Run positions|Meet type|Course|Host):\s*(.+)$",part.strip(),re.I)
            if match:
                field=names[match[1].lower()]
                value=match[2].strip()
                if field in {"season_year","pool_lanes"}:
                    if not value.isdigit():
                        continue
                    value=int(value)
                result[field]=value
    return result
