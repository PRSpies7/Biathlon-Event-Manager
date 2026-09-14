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
4. Click **Generate heats from entries** to generate both disciplines, then review
   the linked programme and athlete tables in each discipline's tab.
   Manual edits remain authoritative; regeneration explicitly replaces assignments.
   Once heats exist, the action is **Regenerate heats from entries**. Its hover tooltip
   states: "This reruns automatic heat generation and replaces the current heat
   assignments, including manual changes." The existing **Replace current assignments
   with newly generated heats** checkbox is still required. Its question-mark
   tooltip explains that ticking it only enables regeneration; assignments change
   only after clicking **Regenerate heats from entries**.
   In **Running/Swimming heat programme**, use **Add heat**, or change **New
   Position** to move an entire heat. Tick **Combine** for two or more heats, then
   click **Combine** to pool and reseed just those heats. They must share a distance.
   Running uses balanced heats of at most 12; swimming uses pool capacity, with
   slower/NT heats first and the fastest heat last. This explicit manual operation
   can combine categories/genders without rerunning automatic grouping elsewhere.
   In **Running/Swimming heat assignments**, edit **Heat** to move athletes in batches,
   or edit seeds and swim lanes. Entering an unused heat number adds it to the draft
   programme too. Heat numbers remain stable while editing; programme positions
   indicate their intended order after saving.
   Enter finishes a cell edit without submitting the form. **Save heat changes**
   applies edits from both disciplines together, removes unused/empty heats and
   renumbers remaining heats consecutively. Added empty heats are temporary until
   populated. Run positions are recalculated from 1, fastest
   outside. Swim heats whose membership changed are reseeded around any explicitly
   edited lanes; unchanged heats keep their lanes. Pool capacity and lane uniqueness
   remain enforced. Automatic grouping is not rerun.
   The selected running/swimming tab is remembered. Counts/categories update when
   a form action submits edits. **Discard unsaved changes** restores both saved
   disciplines. Drafts live only in the current app session until saved. An external
   saved revision change requires reloading rather than overwriting a staged draft.
   Use **Add athlete to this event** for a late entry: number-based history supplies
   valid seeds, otherwise NT. The athlete starts in a new draft heat and can be moved
   in the table. Tick **Remove from event** in either athlete table to remove that
   entry from both disciplines on save. Historical results remain untouched.
   Same-full-name warnings at import/review help identify mistakes without blocking
   legitimate namesakes. Athlete numbers remain the identity key. Review-table seed
   sources and run positions are hidden; Seed and swimming Lane remain visible.
   Reapprove and regenerate operational files after saving assignment changes.
5. Confirm review of both disciplines, approve, and click **Generate operational files**.
   Once files have been generated, this becomes **Regenerate operational files**,
   including after saved edits make the previous files stale and you reapprove.
   The helper states: "Uses the approved heat assignments exactly as currently saved.
   Does not regenerate heats." This action only rebuilds downstream files.
   Continue through the existing phases. Phase 2 retains its runner-movement controls.

## Reverting the table-review change

The initial linked-table review is saved locally at `80bc0f8`. The subsequent
batch-edit, combine and roster refinements can be reverted to that checkpoint.
The earlier interface remains available at `4ff87df`.
There is no database migration or new persistent heat format to reverse. Reverting
the interface does not undo heat assignments or event roster edits already saved; those
remain normal event data. Use **Discard unsaved changes** before saving a draft
you do not want. No GitHub push is part of this change.

## Competition structure

Generation is deterministic and rule-based. It uses current entries, competition
type, capacity and historical seed times; previous heat assignments are never
learning/training data. Manual changes in one event do not influence later events.

The sequence is strict discipline/distance/age/gender groups → sensible same-group
heats → protect satisfactory heats → identify incomplete groups/remainders → combine
compatible whole remainders → compare seeds → compare occupancy → assign programme
order, positions and lanes. Running groups are balanced first (16 → 8 + 8, not
12 + 4); swimming reserves full faster heats and a slower remainder.

`services/competition.py` centralises discipline/distance compatibility tiers.
`services/heats.py` separates grouping, protection reasons, eligibility, destination
ranking, merging and final assignment. Protected heats never donate or receive
athletes automatically. Each successful merge is checked for protection again.

| Event type | Swimming | Running |
| --- | --- | --- |
| Local league | Protect heats with 0–1 empty lanes. With 2+ empty lanes, consider compatible whole remainders. | Protect satisfactory 7–12-person heats; consider smaller compatible groups. Seven is a protection guideline, not a minimum heat size. |
| Interprovincial | Protect heats with 0–2 empty lanes. With 3+ empty lanes, consider conservative combinations. | Protect heats above six runners. Five/six-person heats may remain intact without a strong alternative. |
| National / SA Championships | No automatic age or gender mixing. | No automatic age or gender mixing. |

All combinations require equal discipline distances. Automatic run heats never
exceed 12. NT athletes generally enter slower heats within their competition groups.
Eligible never means mandatory mixing. League ranks category compatibility before
gender, then seed similarity, then occupancy. Interprovincial prioritises same
category/gender and nearby same-gender groups; mixed genders require same/strong
categories and a satisfactory resulting heat. Weak pairs stay separate there.
No weighted occupancy score can override those tiers. Special Needs uses flexible
same-distance options, with gender then seed suitability deciding destinations;
protected Masters heats are never dismantled to accommodate it.
Swim lanes use centre-out seeding; faster runners receive outer starting positions.
For example, seven runners use positions 1–7, with the fastest runner at 7.
Use **Reseed run starting positions** to apply this to saved heats without
regenerating their membership; this replaces manual run-position overrides.
The complete current rules are written out in [HEAT_RULES.md](HEAT_RULES.md).
Special Needs Male and Female both use a 400 m run and a 50 m swim.
Manual unusual combinations/capacities warn; technically invalid outputs are blocked.

Running follows older Masters/Special Needs (women then men), Under 8, Under 9, Under 11,
junior/senior/Masters 40–50, then Under 13/15/17/19. Programme sequence does not imply
combining the listed groups; compatibility and protection govern every combination.
Swimming follows Under 8, older Masters/Special Needs, Under 9/11/13, junior/senior/
Masters 40–50, then Under 15/17/19. Masters 80+ follow the 60+/70+ groups.
Manual exceptions remain authoritative, including run capacity and unusual group
or distance combinations with notices. The existing TimeDrops format still requires
one swimming distance per heat before the operational package can be generated.

## One compatible output package

- **Combined Heats.pdf**: one directly generated document, running then swimming,
  following the repository's accepted PDF reference. Retains blank run finishing
  position/run time and swim time capture areas.
- **Master Entries Heats.xlsx**: the existing heat-section/athlete-row structure.
- **Athlete Run Swim Lane Sheet.xlsx**: athlete, age group, run heat, swim heat and swim lane.
- **Swim Timekeeper Sheets.xlsx**: event name and date on every lane sheet.
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
