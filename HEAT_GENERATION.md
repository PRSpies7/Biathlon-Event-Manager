# Generated and existing heats

In Event Setup, choose **Generate heats from entries** or **Use existing heats**.
Both use the approved Master Entries Excel/PDF parsers and the same saved event.

## Generated path

1. Upload the existing Master Entries Excel format or corresponding combined
   run/swim PDF. Existing assignments establish discipline participation; the
   generator creates new assignments. Source metadata and distances are reused.
2. Check the inferred August–July season and override it if needed. Confirm the
   actual pool capacity, initially suggested from the uploaded document.
   Run positions automatically use 1 through the number of runners, inside to outside; manual position 13
   and above extends the outside edge without extra configuration.
3. Athlete numbers link history automatically; differing names are highlighted
   without blocking, and the uploaded name stays unchanged. Check category, gender, distances and
   seed sources. Current-season fastest takes priority, then previous season,
   then two seasons previously. Wrong-distance/older results cannot supply seeds.
   No usable history produces NT, including visiting athletes.
4. Generate both disciplines, review their tabs, move/swap athletes or edit heat
   numbers, positions and seeds, then save. Lower heat numbers move athletes earlier.
   Manual edits remain authoritative; regeneration explicitly replaces assignments.
   The move/swap controls reseed the affected heats automatically. Use the table
   for explicit position overrides; heat notices are collected in a collapsed panel.
   **Move an entire heat** inserts a selected run or swim heat elsewhere in that
   discipline's programme. Other heats shift and are renumbered; athletes and
   lane assignments within each heat remain intact. Reapprove and regenerate
   operational files after changing the order.
5. Confirm review of both disciplines, approve, and generate the operational files.
   Continue through the existing phases. Phase 2 retains its runner-movement controls.

## Competition structure

Initial heats always preserve age group, gender and correct distance. Optimisation
is a separate pass using the compatibility table in `services/competition.py`.

| Event type | Swimming | Running |
| --- | --- | --- |
| Local league | Consider combining with at least two empty lanes; one empty lane is acceptable. Prefer compatible age, same gender, then similar seeds. | Prefer compatible age, gender and seeds. |
| Interprovincial | Consider combining only with at least three empty lanes. Prefer same gender, compatible age, then similar seeds. | Consider combining only with six or fewer runners, conservatively. |
| National / SA Championships | No automatic age or gender mixing. | No automatic age or gender mixing. |

All combinations require equal discipline distances. Automatic run heats never
exceed 12. NT athletes generally enter slower heats within their competition groups.
Swim lanes use centre-out seeding; faster runners receive outer starting positions.
For example, seven runners use positions 1–7, with the fastest runner at 7.
Use **Reseed run starting positions** to apply this to saved heats without
regenerating their membership; this replaces manual run-position overrides.
The complete current rules are written out in [HEAT_RULES.md](HEAT_RULES.md).
Special Needs Male and Female both use a 400 m run and a 50 m swim.
Manual unusual combinations/capacities warn; technically invalid outputs are blocked.

Running follows older Masters/Special Needs (women then men), Under 8, Under 9–12,
junior/senior/Masters 40–50, then Under 13/15/17/19. Local opening run heats target
at most 10 athletes and may combine compatible younger athletes with older Masters
and Special Needs. Initial groups remain separate before the optimisation pass.
Swimming follows Under 8, older Masters/Special Needs, Under 9–13, junior/senior/
Masters 40–50, then Under 15/17/19. Masters 80+ follow the 60+/70+ groups.

## One compatible output package

- **Combined Heats.pdf**: one directly generated document, running then swimming,
  following the repository's accepted PDF reference. Retains blank run finishing
  position/run time and swim time capture areas.
- **Master Entries Heats.xlsx**: the existing heat-section/athlete-row structure.
- **Athlete Run Swim Lane Sheet.xlsx**: existing mapping output with run position added.
- **Swim Timekeeper Sheets.xlsx**.
- **meet_program.json**: existing TimeDrops IDs, schema and global heat numbering.

The combined PDF and Excel can be downloaded and re-uploaded through **Use existing
heats** without conversion. All files use the same approved run/swim assignments.
The PDF is generated directly as one document; separate PDFs are not merged.

`laneSeedTime` stays zero until its nonzero units/meaning are verified. Actual seeds
and sources remain visible in review. Changes after approval invalidate the files;
review, approve and regenerate, then replace any external copies already downloaded.

Phase 4 saves captured times into shared seasonal history for seeding and Reports.
Points remain blank until published results supply them; existing published results
are protected. Reports select a season without changing historical categories.

See `DATABASE_MIGRATIONS.md` for migration, identity and invalidation details.
