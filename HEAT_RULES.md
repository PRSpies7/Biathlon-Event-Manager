# Current heat-generation rules for review

This describes the deterministic rules currently implemented for organiser
review; it is not an official competition rulebook. Generation uses the current
entries, competition type, capacity and historical seed **times**. Previous heat
assignments are not training data. Manual assignments in one event do not affect
automatic generation in another event.

## 1. Distances

The defaults are the same for male and female athletes.

| Group | Running | Swimming |
| --- | --- | --- |
| Under 8 | 400 m | 25 m |
| Under 9, Under 11 | 400 m | 50 m |
| Under 13 | 800 m | 50 m |
| Under 15, 17, 19 | 800 m | 100 m |
| Junior, Senior, Masters 40+, Masters 50+ | 800 m | 100 m |
| Masters 60+, 70+, 80+ | 400 m | 50 m |
| Special Needs | 400 m | 50 m |

Explicit uploaded distances take precedence over these defaults. The organiser
can correct distances; a difference from the default is highlighted. Different
distances are never automatically combined in one heat.

There are no Under 10 or Under 12 categories. From Under 11 onwards, each youth
category covers two years: Under 11 covers ages 9–10, Under 13 covers 11–12,
Under 15 covers 13–14, Under 17 covers 15–16 and Under 19 covers 17–18.

## 2. Historical seeds

- Match history using the athlete number. A name difference is a notice, not a
  blocker, and the name from the entries stays unchanged.
- Use the fastest valid time for the required discipline and distance in the
  selected season. Only if none exists, try the previous season, then the season
  before that. Never look further back.
- No usable matching time means NT. No time is estimated.
- Seasons run August–July and are named for their ending year. September 2026
  therefore defaults to Season 2027. The organiser can override the season.

## 3. Strict groups, sensible base heats and protection

For each discipline, create separate groups for distance, age category and gender
first. Large running groups are split into reasonably balanced heats with a
maximum of 12: 16 U11 girls become 8 + 8, not 12 + 4. Large swimming groups put their
fastest athletes into full, same-age/gender heats, leaving any remainder in an
earlier, slower heat. Within each group, slower seeds and NT athletes are placed
in earlier heats; faster seeds are placed in later heats.

The pipeline is: strict groups → sensible same-group heats → protect satisfactory
heats → identify remainders → combine compatible remainders → compare seeds →
compare occupancy → assign programme order, positions and lanes.

Protection excludes a heat from both donating and receiving athletes. No athletes
are removed from a protected heat, including for Special Needs placement. Once a
combination becomes satisfactory it is also protected. Incomplete heats are valid;
eligibility is permission to consider a combination, never a requirement to fill it.

The optimisation pass merges whole eligible incomplete heats. A small age/gender group,
such as two Under 19 athletes, stays together rather than being distributed
one athlete at a time across different heats. Full fast swim heats stay intact;
mixing takes place among the slower incomplete heats.

NT athletes stay within their age/gender structure initially. They are not all
collected into one unrelated NT group.

## 4. Programme sequence

This is the starting order, not an instruction to combine every listed group.
Women/girls come before men/boys within each category. The older Masters and
Special Needs block places all its female categories before its male categories.

**Running:**

1. Masters 60+, 70+, 80+ and Special Needs: women, then men.
2. Under 8 girls, then boys.
3. Under 9, Under 11.
4. Junior, Senior, Masters 40+, Masters 50+.
5. Under 13, Under 15, Under 17, Under 19.

**Swimming:**

1. Under 8 girls, then boys.
2. Masters 60+, 70+, 80+ and Special Needs: women, then men.
3. Under 9, Under 11, Under 13.
4. Junior, Senior, Masters 40+, Masters 50+.
5. Under 15, Under 17, Under 19.

After combinations are decided, a combined heat takes the earliest programme
category/gender among its members. Within that category, slower/NT heats come first.
The organiser can subsequently move an entire heat to any place in the programme.

## 5. Local league optimisation

**Running:** 7–12 athletes normally make a satisfactory heat. The automatic
protection guideline is 7; this is not a minimum permitted heat size. Groups of
six or fewer may combine if compatible and the whole groups fit within 12.
An isolated group of five, or even one, can remain intact. Protection also applies
to balanced same-group heats, such as both eight-person heats from a group of 16.
The former opening-heat target of 10 and full-Masters redistribution exception
have been replaced by these protection rules.

**Swimming:** protect full heats and heats with one empty lane. Two or more empty
lanes make a heat eligible. Preserve good faster same-group heats; optimise only
eligible slower remainders. Do not split a small group across destinations.

After enforcing distance, protection and whole-remainder integrity, rank valid
combinations by **category compatibility → same gender → seed similarity →
occupancy**. Category compatibility precedes gender at League. Both age and gender
mixing are allowed within valid tiers; occupancy cannot overcome either preference.

## 6. Interprovincial optimisation

- Running: protect heats of more than six; consider groups of six or fewer.
  A five- or six-person group remains acceptable without a strong alternative.
- Swimming: protect heats with zero, one or two empty lanes. At least three
  empty lanes are needed for consideration.
- Priority: same category/gender → compatible nearby category with the same
  gender → same category with different gender → strong compatible category with
  different gender → seed similarity → occupancy.
- Conservative implementation: same-gender combinations can use strong or
  neighbouring tiers (0–2); weak tier 3 remains separate. Different genders may
  combine only in the same category or strong tier (0–1), and only if the combined
  heat becomes satisfactory (at least seven runners, or at most two empty swim
  lanes). Eligibility alone does not justify combining.
- Protection, whole-remainder integrity, capacity and equal distance apply first.

## 7. National / South African Championships

Keep age categories and genders separate. No automatic mixing. Incomplete heats
are acceptable. Automatic run capacity remains 12; swim capacity is the confirmed
pool lane count.

## 8. Which categories can combine?

Matching event distance is always mandatory, including uploaded distance
overrides. Tiers are **0 same category**, **1 strong**, **2 neighbouring/flexible**,
and **3 weak/last resort**. Unlisted category pairs are incompatible. Special
Needs has the flexible exception described below.

| Discipline / distance | Strong (1) | Neighbouring (2) | Weak (3) |
| --- | --- | --- | --- |
| Run 400 m | U8/U9; any older Masters pair | U9/U11 | U8/U11 |
| Run 800 m | U13/U15; any U15/U17/U19 pair; any adult-cluster pair | U13/U17; U19 with adult cluster | U13/U19; U17 with adult cluster |
| Swim 25 m | Same U8 category uses tier 0; genders may combine where permitted | — | — |
| Swim 50 m | U9/U11; any older Masters pair | U11/U13 | U9/U13 |
| Swim 100 m | Any U15/U17/U19 pair; any adult-cluster pair | U19 with adult cluster | U17 with adult cluster |

Older Masters means 60+, 70+, 80+. The adult cluster means Junior, Senior,
Masters 40+, Masters 50+. U11 and U13 stay standalone whenever their heats are
satisfactory. Older Masters and U8/U9 no longer have a direct automatic pairing;
Special Needs flexibility does not make those otherwise separate groups compatible.

**Special Needs:** any recognised same-distance category is a flexible tier-2
option. Prefer the same gender, then seed suitability. Older Masters is a common
destination, but an eligible younger group can win if its seeds fit better. There
is no forced Masters destination and no exception to protection. Interprovincial
gender restrictions still apply. Equal flexible tiers let seeds influence the
destination before occupancy. No individual athlete is hard-coded.

Every athlete joining a heat must be compatible with every category already
in that heat. Compatibility does not automatically extend through another group.

The optimiser compares all currently eligible pairs and merges the highest-ranked
valid pair, then rechecks protection before considering another merge. It never
dismantles a heat or splits a remainder. This avoids using programme order as an
accidental destination preference. It is a deterministic greedy procedure, not
an exhaustive search for the fullest possible programme.

Seed similarity is the mean absolute time difference across the two groups' known
seeds. Without usable times on both sides, similarity is unknown and ranks after
measured similarity. NT is never given an invented time. Occupancy (fewer empty
spaces) breaks ties only after all grouping and seed preferences. Remaining ties
use athlete numbers, so input row order and previous assignments cannot change
the result.

Implementation: `services/competition.py` centralises discipline/distance category
tiers; `services/heats.py` separates strict grouping, base heats, protection reasons,
eligibility, destination ranking, whole-remainder merging and final assignment.

## 9. Starting positions and swim lanes

**Running:** a heat with N runners uses positions 1 through N. The fastest seed
gets position N, on the outside. The slowest/NT runners receive the lower inside
positions. For example, seven runners occupy 1–7, with the fastest at 7.
Equal seeds are ordered deterministically by athlete number.

**Swimming:** fastest seeds take centre lanes, then work outwards:

- Six lanes: 3, 4, 2, 5, 1, 6.
- Eight lanes: 4, 5, 3, 6, 2, 7, 1, 8.

An incomplete swim heat keeps the centre-lane pattern; it does not start at lane 1.

## 10. Manual review and approval

- Moving or swapping athletes between heats reseeds positions in both affected
  heats. Other heats retain their assignments.
- The running table permits heat and seed edits. Saving automatically recalculates
  all run starting positions from 1, fastest outermost; that column is read-only.
  The swimming table also permits explicit lane overrides.
- Manual run heats can exceed 12, with a notice. Swimming cannot exceed pool
  capacity, and duplicate positions/lanes are blocked.
- Manual exceptional distance combinations produce a warning instead of changing
  automatic rules. TimeDrops still requires a single swimming distance per heat;
  a mixed-distance swim heat must be resolved before generating that output package.
- Moving a whole heat changes its programme position and shifts/renumbers other
  heats. It preserves the athletes and lane assignments within each heat.
- Reseed run starting positions numbers the existing run heats from 1 without
  changing membership; it replaces any manual run-position overrides.
- Review and approve both disciplines before generating the output package.
  Assignment changes invalidate the old files: reapprove, regenerate and replace
  downloaded copies.
