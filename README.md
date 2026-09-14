# Biathlon Event Manager 2.2

A Streamlit + SQLite application for South African biathlon event operations.

The [heat-generation workflow](HEAT_GENERATION.md) adds season-aware entry
import, historical seeds, run/swim generation and manual approval before Phase 1.
Approved heats export to the existing accepted PDF/Excel structures and supply
the operational lane sheets and TimeDrops JSON from one saved state.

Automatic generation is deterministic: strict discipline/distance/age/gender
groups first, balanced running heats or full fast swimming heats next, then
protection of satisfactory heats and combination of compatible whole remainders.
Distance is a hard automatic boundary. League uses category compatibility before
gender; Interprovincial preserves age/gender more strongly; National never mixes
automatically. Seeds are a later preference and occupancy comes last. Special
Needs can use suitable same-distance destinations based on gender and seed times,
without dismantling protected heats. Manual overrides remain available, and previous
heat assignments never train or influence future generation. See the complete
[heat rules and programme sequences](HEAT_RULES.md) for tiers and protection thresholds.

## V1.15 scope

- Phase 1: Upload either the Master Entries Excel workbook or the standard Meet Program PDF through the same uploader. The application detects the format automatically, parses the source into the persistent Master Dataset workflow, then lets the operator review/edit the Phase 1 event settings before initialization. The confirmed settings are used to generate `meet_program.json` and one printable Swim Timekeeper workbook with one tab per swimming lane.
- Phase 2: Start at Heat 1, navigate Previous/Next Heat, jump directly to a heat, optionally combine heats, and capture finishing positions.
- Phase 3: Import one Run Results Excel file and one Swim Results TXT file, validate/map them to the Master Dataset, and persist the results to SQLite.
- Phase 4: Review the final results, manually enter/override runtime and swimtime, normalize times to `MM:SS.ss`, immediately persist manual corrections, reset Phase 4 results when a fresh import is required, and export the existing Master Excel/XML formats.
- Navigation: Open previous saved event sessions and view the current Master Dataset at any time.
- Run TXT timing-button import is intentionally **not implemented** in V1.9. It remains a future enhancement.

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
