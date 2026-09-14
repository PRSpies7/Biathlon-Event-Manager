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
   Nonblocking name/distance notices are grouped in a collapsed **N potential
   issues found** panel. Tick entries to remove and click **Remove selected entries**;
   ticking alone does not remove them. Corrections to remaining entries are retained.
4. Click **Generate heats from entries** to generate both disciplines, then review
   the linked programme and athlete tables in each discipline's tab.
   Manual edits remain authoritative; regeneration explicitly replaces assignments.
   The initialized event shows numbered steps: **1. Choose a heat generation
   profile**, **2. Generate heats from entries**, and **3. Add, remove or confirm
   entries** (changing to **Organise and confirm heats** after generation).
   Before generation, the save action reads **Save entry changes**. Previously
   reviewed duplicate-name notices are not repeated here; a newly added duplicate
   still receives a collapsed notice. Programme columns are Heat, New Position,
   Categories, Athletes, then Combine on the right. Numeric columns use compact
   widths and Categories has a bounded width.
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
you do not want. These checkpoints predate the generation-profile refinement.

## Competition structure

One deterministic generator uses the selected **Heat generation profile**:

| Profile | Behaviour |
| --- | --- |
| League — Efficient | Repack valid same-distance clusters to remove unnecessary heats. Satisfactory heats may participate. |
| Interprovincial — Conservative | Preserve sensible groups, but repair 1–4-runner heats through compatible local placement. Larger run heats can receive a remainder without donating athletes. Swimming still protects heats with at most two empty lanes. |
| SA Champs — Strict | Never automatically mix categories or genders. Incomplete heats are acceptable. |

The selector defaults from event type but can be overridden without changing that
actual event type. Its descriptions explain each policy. **Generated using:** shows
the last saved profile, not an unsubmitted selector choice. A nullable event metadata
field stores the profile and generated revision, also recorded in the audit log,
in the assignment-save transaction. Existing events migrate without rewriting data;
unknown old generation provenance remains blank. Manual edits retain provenance.

All policies form strict distance/category/gender groups first. Running uses
**400 m preferred 10 / hard 12**, **800 m preferred 12 / hard 15**. Preferred sizes
are not hard split points: 14 same-group 800 m athletes can use one heat. Larger
groups split sensibly, e.g. 16 becomes 8 + 8. Swimming never exceeds pool capacity.
Manual Combine remains its existing separate operation, including its 12-runner
split rule; choosing a generation profile does not rerun manual edits or exports.

League evaluates all-pairs-compatible clusters, not just one remainder and one heat.
Within valid arrangements it prioritises heat-count reduction. At equal heat count,
running prefers gender/continuity/category then seed coherence; swimming prefers seed coherence
then gender/category. Preferred sizes and utilisation break later ties. Deterministic
relative seed partitions use no arbitrary time-gap thresholds. NT stays unseeded.
A repack must remove a heat, not merely improve trivial occupancy. Overlapping
clusters are compared deterministically; this is not an exhaustive global solver.
Interprovincial keeps conservative pair merging, with sparse-running repair before
and after it; SA Champs stays strict. Five runners is a sensible-size guideline:
1–3 should be repaired and four reconsidered, without making five a hard minimum.
Repair can move a tiny heat's category/gender blocks to one or two suitable heats;
if intact blocks cannot fit, it may split only that tiny group. Existing larger
groups stay intact. It ranks sparse-size improvement, continuity, gender, seed fit
and utilisation, rather than pursuing League-style minimum heat count.

Running continuity follows U13/U15/U17/U19/Junior/Senior/Masters 40+/50+. Prefer
not to skip an available intermediate category when it offers a compatible,
equally good relative seed fit. This applies to both genders and does not change
the programme sequence. League only adds this structural tie-break to its existing
ranking. Interprovincial U8 singletons may use U9 or older Masters over 400 m,
with no fixed destination preference. **U8 and U11 can never share an automatic
running heat**, even through U9. Final heat checks enforce all pairwise constraints,
distance, profile restrictions and hard capacity. Swimming rules are unchanged.

Distance and category compatibility remain hard feasibility checks. Special Needs
prefers Masters 60+/70+/80+ companions in both disciplines, then the compatible
destination with the closest known seed times if that family is unavailable under
the capacity/profile rules. SA Champs stays strictly separated. Neither history assignments nor manual moves
train future generation. Historical seed lookup remains season/discipline/distance
specific. Swim lanes stay centre-out; faster runners receive higher outside positions.
See [HEAT_RULES.md](HEAT_RULES.md) for full policies and unchanged programme sequences.

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
