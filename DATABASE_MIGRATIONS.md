# Season and heat storage

The existing historical SQLite database holds every season; the operational
database continues to hold sessions. No database is created per season.

Before upgrading an existing schema, initialization creates an adjacent
`<name>.before-seasons-<UTC timestamp>.sqlite` backup using SQLite's backup API,
including committed WAL data. Connections are closed explicitly on Windows.
Migrations run transactionally, preserve IDs/results/awards and the autoincrement
sequence, and check historical foreign keys before commit. Reopening an upgraded
database does not repeat data migration. Restore backups only with the app closed.

Previously unassigned events infer their August–July season from valid dates:
September 2026 belongs to Season 2027. Explicit seasons are preserved. Invalid
dates and conflicting inferred identities remain unassigned for correction.
Known competed categories supply missing competition distances; explicit distances
remain unchanged. Unknown distances cannot supply a seed. Times are never estimated.

`athlete_seasons` stores category by season; original result categories remain
unchanged. The old profile category column remains for compatibility. Reports use
season-scoped events, attendance and awards. Athlete identities, affiliation and
record benchmarks remain shared. Seed lookup uses only the current season and two
previous seasons, with matching discipline/distance and current-season priority.

Captured workflow times use the same historical tables. A persistent session key
makes repeated saves update the same event. Points are not manufactured. Published
imports can replace captured results, but captured times cannot overwrite published
results. Conflicting athlete identities require resolution before saving history.

Operational athlete rows remain the authoritative run/swim assignments and also
store participation, distances, seeds and sources. Events record heat source,
run configuration, assignment revision, approval and export revision. SQLite
triggers invalidate approval/outputs when assignments or relevant metadata change,
including Phase 2 runner moves. Finishing-position mapping and captured times are
separate from starting positions and do not reseed heats.

Every export is built from one approved snapshot and saved together only if that
revision remains current. Concurrent edits require reloading. Stale files are not
offered as current downloads; organisers must replace previously downloaded copies.
