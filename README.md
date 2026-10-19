# Biathlon Event Manager 2.2

A Streamlit + SQLite application for South African biathlon event operations.

The [heat-generation workflow](HEAT_GENERATION.md) adds season-aware entry
import, historical seeds, run/swim generation and manual approval before Phase 1.
Approved heats export to the existing accepted PDF/Excel structures and supply
the operational lane sheets and TimeDrops JSON from one saved state.

Automatic generation uses one deterministic generator with three selectable policies:
**League — Efficient**, **Interprovincial — Conservative**, and **SA Champs — Strict**.
The selector defaults from event type but can be overridden without changing it;
the used profile is saved with the generated revision and displayed during review.
All policies group by discipline/distance/category/gender first. League repacks
compatible clusters to eliminate unnecessary heats, using relative seed coherence
inside valid combinations. Interprovincial protects sensible same-group heats;
SA Champs never mixes categories/genders. Distance always remains a hard boundary.
For running, U8 may join U9 but never U11, even through an intermediate category.
Final compatibility is checked pairwise. Interprovincial repairs 1–4-runner heats
by conservative placement into suitable heats while retaining larger groups;
five is a sensible-size guideline, not a mandatory minimum. Running continuity
favours available intermediate categories with suitable relative seeds. League's
existing optimiser gains only that tie-break and the U8/U11 safeguard; swimming
behaviour is preserved.
Special Needs athletes preferentially join Masters 60+/70+/80+ within valid
generation candidates; otherwise seed similarity selects a compatible destination.
Distance, capacity and profile restrictions remain mandatory.
Running preferred/hard sizes are **10/12 at 400 m** and **12/15 at 800 m**; pool lanes
remain the swimming limit. Manual overrides and output regeneration stay separate.
Previous heat assignments never train future generation. See the complete
[heat rules and programme sequences](HEAT_RULES.md).

## V1.15 scope

- Phase 1: Upload either the Master Entries Excel workbook or the standard Meet Program PDF through the same uploader. The application detects the format automatically, parses the source into the persistent Master Dataset workflow, then lets the operator review/edit the Phase 1 event settings before initialization. The confirmed settings are used to generate `meet_program.json` and one printable Swim Timekeeper workbook with one tab per swimming lane.
- Phase 2: Start at Heat 1, navigate Previous/Next Heat, jump directly to a heat, optionally combine heats, and capture finishing positions.
- Phase 3: Import one Run Results Excel file and one Swim Results TXT file, validate/map them to the Master Dataset, and persist the results to SQLite.
- Phase 4: Review the final results, manually enter/override runtime and swimtime, normalize times to `MM:SS.ss`, immediately persist manual corrections, reset Phase 4 results when a fresh import is required, and export the existing Master Excel/XML formats.
- Navigation: Open previous saved event sessions and view the current Master Dataset at any time.
- Run TXT timing-button import is intentionally **not implemented** in V1.9. It remains a future enhancement.

## Quick Excel to XML conversion

Choose **Quick Tools** in the sidebar, upload an edited final-results `.xlsx`
export, then select **Download Final Results XML**. No event setup is required;
conversion does not change saved sessions. The XML uses the existing final-results
format and the uploaded filename with an `.xml` extension.

Keep the original `Athlete nr`, `Athlete Name`, `athleteSurname`, `runtime`, and
`swimtime` headers. Times accept `MM:SS.ss` and native Excel time cells. Blank or
`00:00.00` times are treated as missing; partial results export the missing time as
`00:00.00`, and athletes with neither time are excluded. Invalid times, missing
names/numbers, duplicate numbers, Excel errors and formulas block conversion.
Replace formulas with calculated values before uploading.

## Important architecture

SQLite is the application's live persistent Master Dataset.

External files are only inputs/outputs:

- Master Entries: `.xlsx` or `.pdf`
- TimeDrops program: `meet_program.json`
- Swim Timekeeper sheets: `.xlsx`
- Run Results: `.xlsx`
- Swim Results: `.txt`
- Final Master: `.xlsx`
- Final Results: `.xml`

Phase 3 writes imported results to SQLite. Phase 4 reads SQLite. Manual Phase 4 corrections are stored as authoritative values and are not overwritten by later imports unless Phase 4 is explicitly reset.

## Requirements

- Python 3.10 or newer
- Windows, macOS, or Linux

## Windows setup

Open PowerShell in the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

If PowerShell blocks script activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

Once dependencies are installed, `run_app.bat` can be double-clicked to start the application.

## Persistent data

The live event database is:

```text
data\biathlon_events.sqlite
```

The application automatically migrates older SQLite databases when required when it starts. The existing athlete/master data and Phase 2 positions are retained.

## Master Dataset

The live dataset contains:

- Athlete Number
- Athlete Name
- Age Group
- Gender (derived for display)
- Run Heat
- Run Lane
- Run Position
- Run Time
- Swim Heat
- Swim Lane
- Swim Time

## Swim Timekeeper workbook

Phase 1 produces one workbook named:

```text
<Event Name> Swim Lanes.xlsx
```

It contains one worksheet per swimming lane. The workbook is designed for printing and repeats the event/title/timekeeper/header block when a lane spans multiple printed pages.

The supplied League 6 swim-lane workbook is used as a layout reference only; its event and athlete data are not copied into generated files.

## Time normalization

Manual Phase 4 time entry accepts common punctuation variations such as:

```text
04:12.50
04;12;50
04,12,50
04.12.50
04 12 50
```

and stores the normalized value as:

```text
04:12.50
```

## Phase 4 reset

`Reset Phase 4 Results` clears imported and manually entered runtime/swimtime values only. It does not clear athlete information, heats, lanes, or Phase 2 run positions.

## Final exports

The Master Excel export and XML export retain the existing V1 output structures. The Phase 4 Age Group display is for operator reference only and is not added to either final export.

The XML declaration is generated as:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
```

## Tests

Run:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The test suite covers the original parser tests plus time normalization, manual-time persistence/reset behaviour, and the Swim Timekeeper workbook.

## PDF Master Entries input

The Phase 1 uploader accepts `.xlsx` and `.pdf` without a file-type selector. For the standard Meet Program PDF format, the parser reads the Running Heats and Swimming Heats sections and maps athlete number, athlete name, age group, heat, and lane into the same canonical Master Dataset used by the Excel parser.

When a PDF is uploaded, Phase 1 does not initialize the event immediately. Instead, sensible defaults are pre-populated for review: the meet name and date are inferred from the filename when possible, pool lane count is inferred from the highest swimming lane, and the established defaults are used for host/team, course, and TimeDrops timezone. The operator can edit these values before clicking `Confirm Data Set and Initialize Event`. The final confirmed settings are then persisted to SQLite and used to generate `meet_program.json` and the Swim Timekeeper workbook.

## Table theme

The Streamlit theme configuration deliberately uses a white dataframe canvas and a white dataframe header with a navy application text colour. This is intentional because Streamlit's native dataframe/editor grid uses the theme configuration for its rendered grid canvas. The application page remains the light grey-blue `#EEF1F5`, so tables retain clear visual separation from the page.

## Season Results Database

The independent **Season Results Database** sidebar module imports published
league, interprovincial and Gauteng North Championship results, tracks season
affiliation and event awards, and provides seven Excel reports including school
team rankings and qualification. See
[Season Results Database V1](SEASON_RESULTS_DATABASE.md) for usage, persistent
SQLite configuration, supported layouts and deployment limitations.

### Event runtime files

Disposable event files live beside the event database in
`data/runtime/event_<event_id>/{uploads,outputs,temp}/`. Operational PDF, Excel
and TimeDrops JSON packages, run position workbooks and final Excel/XML exports
are saved in `outputs`. Uploads are processed in memory; no extra copies are made.
Operational downloads retain approval/revision checks and verify file integrity.
Legacy database-only packages need explicit regeneration before downloading.

Reset Sessions still clears all saved event sessions. Its optional **Also delete
event files** checkbox removes only those sessions' runtime workspaces. Unchecked,
it keeps their files. Missing workspaces are harmless. Historical season results,
source, fixtures, examples, reference documents and templates are never targeted.
Runtime workspaces are ignored by Git. The old `data/generated` event JSON copies
were disposable exports and have been removed; reference documents remain intact.

### Results Verification

Use **Manual Results Verification** in Event Management Step 4, or the standalone
**Results Verification** module. Both use the same engine and review panel.
The standalone module accepts final-results XML, Master Results Excel, and the
existing published season-results Excel/PDF formats; it never imports into history.

Upload both manual Run and Swim PDFs, then select **Verify Results**. Athlete ID
has priority; exact normalized names are a fallback, and ambiguous matches require
correction. Differences up to and including 0.40 seconds pass. Differences through
1.00 second require a choice; larger differences are warned and shown first.
Choose **Use Electronic** or **Use Manual**, then **Apply Selected Results**.
Unselected issues never change results. Step 4 uses its existing manual-time update
path and refreshes its authoritative table and exports. It does not calculate
competition scores/rankings; published season scores are preserved independently.

Scanned PDFs are recognized locally using RapidOCR/ONNX Runtime. Install the
optional dependencies with `.venv/Scripts/python.exe -m pip install -r requirements-ocr.txt`.
They are already installed in this working environment. No API key is needed and
PDFs are not uploaded to a service. Both verification interfaces invoke the same
recognition adapter automatically when a page has no text layer.

The adapter locates printed athlete rows in the known run/swim layouts and reads
individual time boxes. Each proposed reading includes an image of the original
row. All OCR readings remain unconfirmed, regardless of recognition scores.
Review the ID and handwriting before choosing Electronic or Manual; correct
misread IDs/times under **Review or transcribe manual readings**, then recheck.
Missing rows remain issues. Blanks and crossed-out rows are never automatically
converted into recorded results. Very different layouts or poor scans may need
manual transcription.

`N/S`, `NS`, and `DNS` mean did not start; selecting Manual clears the relevant
captured time. Compact times such as `106.44`, `10944`, `1.1708`, and alternative
separators such as `40:12` are proposed as formatted times and require review.
The local sample check used the first page of each supplied League 2 PDF: 19 run
rows and 21 swim rows were detected. Some digits were misread, particularly on the
run sheet; this is assisted transcription, not validated unattended recognition.

Recognition models are provided by [RapidOCR](https://github.com/RapidAI/RapidOCR).
Models are cached in the Python environment and are not event runtime outputs.
