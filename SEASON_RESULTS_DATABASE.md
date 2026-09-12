# Season Results Database V1

Open **Season Results Database** in the sidebar. This is independent of the four
event-management phases and their saved sessions. Upload only final, published
results from the season represented by the selected database.

## Use

1. In **Import Results**, upload one or more PDF / `.xlsx` files and select
   **Preview results**. No database results change at this stage.
2. Check the source filename, detected event name, date, competition type, result
   count and awards count. **Event details** allows brief metadata corrections.
   Dates come from document contents, never a potentially misleading filename.
3. Existing events prompt: **This event already exists. Overwrite the existing
   event results or skip this event?** Choose **Overwrite** or **Skip**. Skip is
   the default. Duplicate identities within a batch receive the same choice.
4. Select **Import selected results**. Each event is a separate transaction.
   Overwriting removes its entire old result and award set and inserts the new
   set atomically, retaining its event ID. A failed transaction rolls back that
   event; previously completed events in the batch remain saved.
5. **Imported Events** lists saved events and shows the earliest imported event
   date as the current season start. **Athlete Database** supports search,
   affiliation filtering, individual results and manual affiliation corrections.
   Back / Continue buttons follow the same style as Event Management navigation.
   Report descriptions use hover help beside each title; download buttons sit
   directly below. On-screen qualification previews are collapsible.
6. **Reports** provides seven Excel downloads: full database, primary/high school
   results, qualified schools, affiliated athletes, qualified athletes, top athletes, and records. See the report
   rules below. The full database includes Athletes, Event Results, Imported Events
   and Event Awards sheets, plus Current Records when references have been saved.
   The Athletes sheet has one row per season athlete, `Affiliated` /
   `Not Affiliated`, attendance counts and one readable awards column.
7. The orange **Reset Database** button on **Athlete Database** opens a warning
   with **Cancel** and **Confirm Reset Database**. Confirmation permanently clears
   all season events, athletes, affiliation information, results, awards and saved
   current record references in
   one transaction. It also clears the current browser's import previews.
   Event Management sessions remain intact. Export or back up anything you need
   before resetting; the action cannot be undone.

## Report rules

Reports show athlete number, name, age group and school. Result reports also show
run time, swim time and total points. They sort age groups from youngest to oldest
(under-age groups, juniors, seniors, then masters), with total points descending
within each age group. Non-numeric totals such as DNF follow numeric scores.
Categories without a defined age, such as Special Needs, follow the age groups.

One-row-per-athlete summaries use the athlete's latest event age group and the
highest published total within that group. Run time and swim time come from that
same result; its event is identified. Full event-result sheets retain each
published performance. The school and affiliation fields retain known season
information as described below.

- **Full database**: all saved season data in normalized sheets. Current record
  references include their source filename and import timestamp.
- **Primary schools and high schools results**: athletes with a nonblank known
  school, including their event results and awards. No school type or age is
  guessed. A later result without school text can use the athlete's known school
  in this report; this does not change the stored event result.
- **Affiliated athletes**: athletes currently marked affiliated, including their
  school, age group, times, event details and awards. All points columns are
  omitted from this workbook. Manual affiliation corrections affect this report.
  Its second sheet, **Insights**, counts and lists all season athletes who attended
  at least two events without affiliating, including those outside the main sheet.
- **Qualified schools**: a school ranking plus a School Athlete Scores sheet with
  all eligible athletes, affiliation, selection/place, qualification shortfalls,
  best score and its event/date, counted contribution, and every event's raw total.
  Names ending in `Ps` use primary rules; `Hs` use high-school rules (case ignored).
  Unrecognized suffixes remain visible with a missing-type explanation and no
  invented score. Primary teams require one athlete each from U9, U11, U13 and
  U15, followed by two extras. High teams require U15, U17 and U19, followed by
  three extras. Boys and girls share places. Each athlete occupies only one place.
  Qualified athletes take priority in each place; among them the highest score
  wins. When no qualified replacement exists, an unqualified athlete can contribute
  but the school is not yet qualified. Missing mandatory groups leave only their own
  places empty; eligible extras still contribute (two primary, three high). A high
  school missing one mandatory group can count five athletes, or four when two are
  missing. Extra athletes cannot fill the missing mandatory places.
  Extras come from the school's eligible age groups or Special Needs; at most one
  Special Needs athlete can be selected, capped at 2,000 for selection/contribution.
  Published scores remain unchanged in event columns. The best completed result
  in the athlete's latest category provides their score, from any meet. Their
  latest dated nonblank school identifies the school team, with profile fallback.
  School qualification requires a complete six-person team whose selected athletes
  each completed at least four distinct league, interprovincial or GN Championship
  events, including at least one interprovincial or GN Championship. Any mix of
  those event types counts: two leagues plus two interprovincials qualify, as do
  two leagues plus the championship plus an interprovincial. Four leagues alone
  do not qualify; two leagues plus the championship alone are only three events.
  Completion uses the same positive run/swim-time
  and status rules as athlete qualification. Attendance is counted once per event
  toward the four required places, across the athlete's season. Both qualification
  reports share the same event-count logic. Totals rank highest first across primary and high schools;
  equal totals share a rank. Qualification cells are green for Yes and red for No;
  qualified school names are also green, both on screen and in Excel.
  The workbook also includes **Primary Schools** and **High Schools**, each ranked
  independently by school points (ties share rank). Both tabs and **Qualified Schools**
  separate **Full team** (Yes/No), **Missing team members** (e.g. 1 Under-15 athlete),
  and **Qualification requirements** (e.g. Under-15: interprovincial or GN Championship
  required). Qualification summaries state event types or a score requirement by age
  group without athlete names or event counts; the full detail retains both.
  A full team can still be unqualified. Columns fit content within reasonable limits; long
  missing-requirement text wraps at a fixed width.
- **Qualified athletes**: athlete summaries ranked by age group and highest total,
  with attendance count and two additional columns:
  `Qualified` (Yes/No) and `Missing to qualify`. Non-qualified athletes remain in
  the report. Missing requirements show the additional completed events needed and
  whether an interprovincial/championship is still required; qualified athletes show `None`.
  Qualification requires at least four distinct completed league, interprovincial
  or Gauteng North Championship events, including at least one interprovincial or
  championship. JNR/junior, senior and all master age groups require three distinct
  completed events, also including at least one interprovincial or championship.
  Any combination counts: two leagues plus two interprovincials qualify younger
  athletes; four leagues alone do not. Championships count once, never twice.
  Both athlete and school qualification also require a best completed score in the
  latest category of at least 1,890 points, or 1,790 for juniors, seniors and masters.
  These include the accepted 10-point allowance below the nominal 1,900/1,800.
  Missing requirements include score shortfalls. Athlete names and their adjacent
  Qualified cells are green for Yes and red for No. Insights is the second sheet.
  The athlete's category from the most recent event by date determines the rule.
  Each distinct event counts once. Both running and swimming must have positive
  published times; DNF, DNS, disqualification, missing and zero times do not count.
  Affiliation is displayed but is not an additional qualification condition.
  This report includes school, affiliation and the highest total only,
  without per-event scores, run/swim times or discipline points. Qualification is assessed once
  per athlete using the most recent event age group and applies to each of their
  age-group rows if they changed categories during the season.
- **Top athletes**: all athletes with season results, ranked within each age
  group by their highest single-event published total. Includes athlete number,
  name, age group, school, province/team, affiliation, attendance count, highest
  total and one total-points column per event. Equal highest scores share a rank
  (1, 1, 3). Missing-event cells are blank; published DNF and zero totals remain
  visible. Athletes without a numeric score have a blank rank at the end of their
  group. If an athlete competed in different age groups, each group gets its own
  row with only the scores achieved in that group. Event columns are generated
  only for this Excel report; the database remains normalized.
  **Insights** is the second sheet. **Event Details** adds run/swim times, discipline
  points, bonus points and total for each event. Qualified Athletes includes totals
  without this additional discipline detail.
- **Records**: download the current-records template, enter category, record
  holder's athlete number and total points (name optional), upload, preview and
  save it. Unfilled category rows are ignored. Saving atomically replaces the
  complete reference list. Reference holders need not be season participants.
  References persist in the season database, in `season_record_benchmarks`.
  The report lists published total points exceeding or equalling the supplied record
  in the same category, with school, run/swim times, the reference holder, points
  and difference, sorted by age group and descending total.
  Categories without references are identified in the UI and are not compared.
  This compares final published totals without recalculating scores or updating
  record references automatically. Every comparison is against the supplied
  reference, rather than an inferred sequence of records during the season.
  The formatted **GN records workbook** can also be uploaded directly, without
  athlete numbers. `RECORD POINTS` is authoritative, not `OLD RECORD`; floating-point
  residue is normalized to published two-decimal precision. The uploaded workbook
  is stored in `season_record_templates` atomically with its references.
  **Download updated records list** preserves its layout, formulas, SA-record values
  and unchanged category records. Strictly higher published season bests update the
  holder, old/current points, GN marker, season (event year), meet and run/swim times.
  Equal scores retain the existing holder; tied new bests use the earliest occurrence.
  The title year follows the latest imported event year. **New Records** includes
  athlete numbers and event names/dates. Downloads do not modify the saved template
  or references. Saving a new reference list or resetting the database clears the
  previous template. Categories absent from the template are flagged, not invented.

**Insights** in Top Athletes and Qualified Athletes includes participation by event
(chart), latest age groups with fewer than six athletes (chart), top-three category
performers who attended only one event, and affiliation follow-up. Insights attendance
counts distinct imported results including non-finishers; qualification still requires
completed events. Top-three uses best completed scores in the latest category, including
ties. Categories with no season data cannot be inferred. These are season snapshots.

Record category matching ignores case, extra whitespace, under-age slash/leading
zero formatting, and singular/plural junior, senior and master labels. Different
age groups and sexes remain separate. There is one supplied reference per category.
Sex-first record labels such as `GIRLS U/11` match `U/11 GIRLS`.
Records also recognize Under/U labels, hyphens, singular/plural labels and equivalent
boy/male/man or girl/female/woman labels within the same age bracket. Matching never
crosses sex or age boundaries. Only category and record points are required; holder
details are optional. Preview immediately shows equal/higher published total scores
without requiring run/swim times. Save persists the references and original template.

## Persistence and configuration

The default is `data/season_results.sqlite`, separate from
`data/biathlon_events.sqlite`. Data survives browser closure and application
restarts. **Reset Sessions** does not delete season data.

One database file represents one season. For a new season, configure a different
file and restart the app. Keep the previous file as an archive. There is no
cross-season merging or automatic calendar-year classification.

Configuration precedence:

1. `DATABASE_URL`, if set: V1 accepts a plain `sqlite:///...` file URL.
2. `SEASON_DATABASE_PATH`: a SQLite file path.
3. The default `data/season_results.sqlite` under the application directory.

Relative paths resolve against the application directory. Absolute SQLite URLs
use `sqlite:////...` on POSIX or `sqlite:///C:/...` on Windows. These settings
apply only to this module; the existing workflow configuration is unchanged.
Memory databases and unsupported URL schemes are rejected, without a silent
local fallback. No credentials are required for SQLite.

Use local persistent storage, or an explicitly mounted durable volume on a
host. **Do not deploy this SQLite V1 onto Streamlit hosting with only an
ephemeral filesystem.** PostgreSQL is not implemented in V1; its connection,
schema and repository adapter must be added before deployment to such a host.
The UI, import models and exporters do not contain SQL or assume SQLite IDs
beyond the repository's interface. No external database account is configured.

Back up the season file while the app is stopped (including any outstanding WAL
files), or use SQLite's online backup API while it is running. Excel is a readable
export, not a database restore format. Never commit databases, secrets or local
configuration values.

## Stored data and import rules

Future interprovincial imports retain only explicit GN / Team GN / Gauteng North
teams, including GN Team A/B. When team is blank, an explicit GN province is used.
Other and unidentified teams are excluded along with their awards, with exclusion
counts in the import preview. Existing imports are not cleaned automatically.
Re-importing with Overwrite applies the filter to that event's replacement results.

- `season_events`: internal ID, normalized event identity, name, date, type,
  source filename and UTC import timestamp. Identity/date/type is unique.
  Case, whitespace, punctuation and interprovincial hyphenation do not create
  separate events. Meaningfully different event names remain distinct; correct
  an alias in the preview if necessary.
- `season_athletes`: season-wide unique athlete number, canonical name, school,
  category, province, team and affiliation. Athlete numbers remain text,
  preserving leading zeroes. Name matching is not used for identity.
- `season_results`: event/athlete link, event-specific name, category, position,
  published times/points, status, school, province, team and annotations.
  Times and points are stored as source text so `DNF`, published zeroes and
  precision remain representable. Numeric points become numeric Excel cells.
- `season_awards`: event/athlete link, Runner / Swimmer / Overall Athlete and
  placing 1–3, with a foreign key to that athlete's event result.

`(AFL)` and `(AFL*)` both promote affiliation and are removed from names.
Automatic imports never demote affiliation; manual corrections can set either
value. `(TO)` is stored as an annotation and is not affiliation. PB markers are
discarded while the athlete, times and published scores remain. Scores and
award rankings are never recalculated.

Blank school/province/team/category data cannot erase useful season athlete
information. Nonblank values and the canonical name reflect the latest import;
each event retains its own source values. Athletes removed by an overwrite
remain in the season directory with any previously learned affiliation/school
information and an accurate attendance count (possibly zero). This avoids
silently discarding payment-follow-up information.

## Parser architecture and limits

- `parsers/season_results/league_pdf.py`: ruled league tables, including wrapped
  school/name cells and category headings continued on subsequent pages.
- `parsers/season_results/interprovincial_pdf.py`: header-derived column geometry
  and horizontal row rules, joining name/team fragments over page breaks.
- `parsers/season_results/excel.py`: header-mapped workbook tables. Province/team
  columns distinguish the interprovincial structure from league tables.
- `common.py` and `models.py`: shared normalized results/awards and metadata,
  separate from persistence and the existing upstream result-processing service.

Gauteng North Championship / GN Championship (including Champs and plural forms)
is recognized from the event title. Championships reuse the league or
interprovincial layout adapter according to their table headers. No separate
championship scoring or result recalculation is introduced. The existing text
competition-type column stores the new type without a schema migration.

The supplied league PDF has a 2025 filename but an internal date of 2026-08-25;
the internal date is used. The supplied national-titled Excel example is read
only as an interprovincial structural example. An unsupported title requires
explicit name/type confirmation. This does not implement national competition
rules or a national PDF adapter.

Supported layouts are the supplied report families, not arbitrary spreadsheets
or PDFs. Scanned PDFs/OCR, missing athlete numbers, multiple events within one
file, and multiple category-result rows for one athlete in the same event are
not supported. Import stops on ambiguous/missing identity or recognizable lost
PDF rows rather than guessing identities or silently replacing with partial
data. PDFs with broken font encoding may contain unreadable name characters;
use Excel when available. There is no manual score-validation workflow.

## Verification

Run `python -m pytest -q` with `requirements-dev.txt` installed.
`tests/test_season_results.py` builds small synthetic Excel/PDF fixtures in memory
with anonymous athletes. `tests/test_season_results_ui.py` exercises Streamlit
navigation, batch import, duplicate decisions, overwrites and affiliation with
temporary databases. No supplied result documents or generated databases are
added as fixtures.
`tests/test_school_reports.py` covers school team selection, qualified replacements,
missing groups, special-needs caps, championship attendance/import, school ranking
and Excel qualification colours.
