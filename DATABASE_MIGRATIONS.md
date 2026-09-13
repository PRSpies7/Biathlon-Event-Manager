# Season database foundation

The existing `data/season_results.sqlite` (or configured historical database)
stores every season. `data/biathlon_events.sqlite` continues to store operational
sessions. No database is created per season.

## Migration safety

On first initialization of an older schema, the application creates an adjacent
`<name>.before-seasons-<UTC timestamp>.sqlite` backup using SQLite's backup API,
including committed WAL data. Backup failure stops initialization. Schema changes
then run in a transaction; failure rolls back the migration. Historical parent
table replacement preserves event IDs, its autoincrement sequence, results and
awards, and checks foreign keys before commit. Reopening an upgraded database
does not repeat the migration or create another backup.

Migration does not infer seasons from dates or distances from historical labels.
Existing values remain intact, with unknown season/distance fields set to NULL.
Legacy events are visible under **Unassigned (legacy)** and can be assigned a
season explicitly. Keep the backup; restoration should be performed with the app
stopped and all database connections closed.

## Storage and queries

- Operational `events` and historical `season_events` have nullable `season_year`.
  New UI imports require an explicit season value. Nullable repository inputs
  remain supported for legacy compatibility; the import service requires a season.
- Results inherit season through their event. Event deduplication includes season,
  including a separate uniqueness guard for unassigned events.
- `athlete_seasons(athlete_id, season_year, category)` stores category by season.
  Result categories retain exactly what was imported. Seasonal category summaries
  use the latest event date (event ID breaks ties), independently of import order.
  The original athlete profile category column remains for legacy compatibility
  and is no longer overwritten by subsequent imports.
- `season_results.run_distance` and `swim_distance` store positive integer metres
  when supplied. Unknown distances are excluded from distance-matched lookup.
- `season_snapshot(path, year)` scopes events, results, attendance and awards to
  that year; `None` selects legacy records. The default all-season snapshot remains
  available to existing internal callers. Interactive Reports pass the selected year.
- `historical_performances` returns only matching discipline/distance candidates
  from the requested and immediately preceding seasons, with source event, category,
  date, time and status. Seed selection/validity rules belong to the later seed engine.
- Athlete identity, affiliation and record benchmarks remain shared. Category
  membership and competed result categories are season-specific. Full identity
  ambiguity resolution and generated-entry integration belong to subsequent stages.

Focused tests cover legacy backup/migration/idempotency/rollback, category changes,
season correction, scoped reporting and resets, and historical distance boundaries.
