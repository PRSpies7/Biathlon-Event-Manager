"""Combined operational heat document and re-importable Master Entries workbook."""
from collections import defaultdict
from io import BytesIO
import json
from math import ceil

from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment


def metadata(event):
    return [f"Event: {event['name']}",f"Date: {event['start_date']}",f"Season: {event['season_year']}",
        f"Pool lanes: {event['pool_lanes']}",f"Run positions: {','.join(map(str,json.loads(event['run_positions'])))}",
        f"Meet type: {event['meet_type']}",f"Course: {event['course']}",f"Host: {event['host_team']}"]


def groups(rows,prefix):
    heats=defaultdict(list)
    for row in rows:
        if row.get(prefix+"_heat") is not None:
            heats[row[prefix+"_heat"]].append(row)
    return [(number,sorted(members,key=lambda r:(r[prefix+"_lane"],str(r["athlete_number"])))) for number,members in sorted(heats.items())]


def group_label(row,discipline):
    distance=row.get(discipline+"_distance")
    return f"{row.get('group_name') or 'Unspecified'}" + (f" ({distance}m)" if distance else "")


def build_heats_xlsx(rows,event):
    wb=Workbook()
    ws=wb.active
    ws.title="Heats"
    for line in metadata(event)[:3]:
        ws.append([line])
    for discipline,prefix in (("run","running"),("swim","swimming")):
        ws.append([])
        ws.append([prefix.title()+" Heats"])
        for heat,members in groups(rows,prefix):
            ws.append([f"Heat {heat} - "+"; ".join(dict.fromkeys(group_label(r,discipline) for r in members))])
            ws.append(["#","Athlete","Group","Lane","Pos" if discipline=="run" else "Position","Time"])
            for r in members:
                ws.append([str(r["athlete_number"]),r["athlete_name"],group_label(r,discipline),r[prefix+"_lane"],None,None])
                ws.cell(ws.max_row,1).number_format="@"
            ws.append([])
    rule=Side(style="hair",color="CCD6DF")
    for row in ws:
        for cell in row:
            cell.alignment=Alignment(vertical="center",wrap_text=True)
            cell.border=Border(bottom=rule)
            if isinstance(cell.value,str):
                cell.data_type="s"
        ws.row_dimensions[row[0].row].height=25
        if row[0].value=="#" or str(row[0].value or "").startswith(("Heat ","Running Heats","Swimming Heats")):
            for cell in row:
                cell.font=Font(bold=True,color="244761")
        if row[0].value and all(cell.value is None for cell in row[1:]):
            ws.merge_cells(start_row=row[0].row,start_column=1,end_row=row[0].row,end_column=6)
            ws.row_dimensions[row[0].row].height=max(25,ceil(len(str(row[0].value))/95)*14+8)
    for col,width in {"A":12,"B":34,"C":36,"D":10,"E":12,"F":22}.items():
        ws.column_dimensions[col].width=width
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation="landscape"
    ws.page_setup.paperSize=ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth=1
    ws.page_setup.fitToHeight=0
    output=BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def build_heats_pdf(rows,event):
    """Match the accepted sample: running then swimming, repeated heat tables.

    Fixed columns and single-line athlete rows remain compatible with the input
    parser. Generous row height leaves handwritten finishing position/time space.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase.pdfmetrics import stringWidth
    output=BytesIO()
    pdf=canvas.Canvas(output,pagesize=A4)
    pdf.setTitle(f"{event['name']} - Running and Swimming Heats")
    width,height=A4
    dark=HexColor("#244761")
    line=HexColor("#D5DEE5")
    page=0
    y=0
    def text(x,y,value,size=8.5,max_width=None):
        value=str(value)
        if max_width:
            measured=stringWidth(value,"Helvetica",size)
            if measured>max_width:
                size=max(5.5,size*max_width/measured)
        pdf.setFillColor(dark)
        pdf.setFont("Helvetica",size)
        pdf.drawString(x,y,value)
    def new_page(prefix):
        nonlocal page,y
        if page:
            pdf.showPage()
        page+=1
        text(26,height-28,prefix.title()+" Heats",12)
        text(26,height-44,metadata(event)[0],9,max_width=540)
        text(26,height-57," | ".join(metadata(event)[1:4]),8)
        text(26,20,f"Season {event['season_year']} | Revision {event['heat_revision']} | Page {page}",8)
        y=height-77
    def heading_lines(heat,members,discipline):
        description="; ".join(dict.fromkeys(group_label(r,discipline) for r in members))
        words=f"Heat {heat} - {description}".split()
        lines=[]
        current=""
        for word in words:
            candidate=(current+" "+word).strip()
            if stringWidth(candidate,"Helvetica",8)>width-52 and current:
                lines.append(current)
                current=word
            else:
                current=candidate
        return [*lines,current]
    def heading(heat,members,discipline):
        nonlocal y
        pdf.setStrokeColor(line)
        pdf.line(26,y,width-26,y)
        labels=[(26,"#"),(94,"Athlete"),(250,"Group"),(395,"Lane"),(435,"Pos" if discipline=="run" else "Position"),(489,"Time")]
        for x,label in labels:
            text(x,y-14,label,8)
        y-=23
        pdf.line(26,y,width-26,y)
        for value in heading_lines(heat,members,discipline):
            text(26,y-14,value,8)
            y-=12
        y-=8
    for discipline,prefix in (("run","running"),("swim","swimming")):
        new_page(prefix)
        for heat,members in groups(rows,prefix):
            needed=31+12*len(heading_lines(heat,members,discipline))+min(len(members),12)*23
            if y-needed<40:
                new_page(prefix)
            heading(heat,members,discipline)
            for row in members:
                if y<63:
                    new_page(prefix)
                    heading(heat,members,discipline)
                y-=23
                text(26,y+9,row["athlete_number"],8.5,60)
                text(94,y+9,row["athlete_name"],8.5,150)
                text(250,y+9,group_label(row,discipline),8,137)
                text(397,y+9,row[prefix+"_lane"],8.5)
                pdf.setStrokeColor(dark)
                pdf.line(435,y+5,465,y+5)
                pdf.line(489,y+5,width-28,y+5)
                pdf.setStrokeColor(line)
                pdf.line(26,y,width-26,y)
            y-=12
    pdf.save()
    output.seek(0)
    return output
