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

## 3. Generation profiles and base heats

The selector **Heat generation profile** defaults to the event type, but may be
changed deliberately without changing the competition type. The policies are
**League � Efficient**, **Interprovincial � Conservative**, and **SA Champs � Strict**.
The profile and generated revision are saved atomically with assignments and in
the audit log. Review displays **Generated using:** the last generation policy.
Manual edits retain this provenance; selecting a profile alone changes no heats.
Older events have unknown provenance until regenerated, rather than a guessed label.

All profiles start with discipline/distance/category/gender groups. Running uses
preferred/hard capacities of **10/12 for 400 m** and **12/15 for 800 m**.
Preferred is not a split point: 14 same-group 800 m runners can use one heat;
16 must split, normally 8 + 8. Balanced sizes avoid tiny additional run heats.
Other explicitly supplied run distances retain the former maximum of 12.
Swimming reserves full faster base heats and a slower remainder, within pool
capacity. NT is unseeded/slower, never an invented time.

Interprovincial protects satisfactory heats and merges only compatible whole
remainders. SA Champs never mixes groups. League instead searches compatible
clusters and may repartition satisfactory heats when it removes an entire heat.
No profile mixes distances or uses previous heat assignments as training data.

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

## 5. League � Efficient

Compatibility defines feasibility; heat count and seed coherence choose among
feasible arrangements. A good same-group heat is preferred, not immutable. It can
receive a remainder or be repartitioned with compatible categories if that removes
an unnecessary heat. Without a heat-count reduction, good heats remain unchanged.

The optimiser considers whole same-distance, all-pairs-compatible category pools,
including same-gender alternatives and overlapping pair clusters. A compatible
bridge does not permit a forbidden pairing. For each candidate pool it targets
ceil(athletes / hard capacity) heats and compares deterministic seed-, gender- and
category-ordered partitions, with balanced, preferred-size and full-heat options.
It applies the best heat-count reduction and repeats. This is a deterministic
candidate search, not a claim of exhaustive global optimisation across overlapping
incompatible clusters.

Within valid candidates, fewer total heats comes first. For **running**, equal-count
solutions prefer same gender, nearer category tiers, seed coherence, then preferred
size and balanced utilisation. For **swimming**, equal-count solutions prefer seed
coherence, same gender, nearer category tiers, then balanced utilisation. Seed
coherence separates NT where practical and compares within-heat squared deviations
of known times; there are no absolute time-gap thresholds or invented NT values.
Athlete numbers break final ties. Occupancy never legitimises an incompatible pair.

Thus 8 older Masters + 2 Special Needs can run together over 400 m; 15 compatible
800 m runners can use one heat. A valid six-lane cluster of 5 + 5 + 6 + 2 swimmers
can become 6 + 6 + 6. Juniors can be split between faster Seniors and slower Masters
when their relative seeds suit those heats. No category has a hard-coded destination.
A small heat remains acceptable when reducing it would violate compatibility.
Repacked blocks use their earliest category programme position, with slower/NT
heats first and faster heats last; standard position/lane seeding still applies.

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
are acceptable. The distance-aware running hard limits are 12 (400 m) and 15
(800 m); swim capacity is the confirmed pool lane count.

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
Masters 40+, Masters 50+. Interprovincial preserves satisfactory U11/U13 heats;
League may repack them within valid neighbouring clusters to remove a heat. Older Masters and U8/U9 no longer have a direct automatic pairing;
Special Needs flexibility does not make those otherwise separate groups compatible.

**Special Needs:** any recognised same-distance category is a flexible tier-2
option. Older Masters or suitable younger groups can be destinations. League
compares performance within valid clusters, with running gender/category preferences
and swimming seed coherence as described above. Interprovincial retains protection
and gender restrictions. No individual athlete is hard-coded.

Every category in a generated heat must be compatible with every other category.
Interprovincial compares eligible whole-remainder pairs, then rechecks protection
following each merge. Its seed similarity uses mean absolute known-time differences,
with unknown similarity last. League uses cluster partition comparisons instead.
Implementation is centralised in `services/competition.py` (profiles, capacities,
compatibility) and `services/heats.py` (base heats, profile policies and assignment).

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

- Each discipline has programme and athlete tables in one shared form. Add a draft
  heat, edit **New Position** to reorder whole heats, or move/swap athletes by editing
  their Heat cells. Enter does not submit; explicit buttons apply edits. The selected
  discipline stays active. Counts/categories refresh on form submission.
- **Save heat changes** saves both disciplines together, removes all empty
  heats and closes numbering gaps. Draft heat
  IDs remain stable while editing; saved heat numbers follow the programme order.
  **Discard unsaved changes** restores both disciplines to the saved state.
- Moving or swapping athletes between heats reseeds positions in both affected
  heats. Other heats retain their assignments.
- The running table permits heat and seed edits. Saving automatically recalculates
  all run starting positions from 1, fastest outermost; that column is hidden.
  Saving swim table membership changes reseeds only affected heats, reserving any
  explicitly edited lanes. Other heats keep their lanes. The swimming table permits
  explicit lane overrides; these must be unique and within the pool.
- Manual run heats can exceed 12, with a notice. Swimming cannot exceed pool
  capacity, and duplicate positions/lanes are blocked.
- Manual exceptional distance combinations produce a warning instead of changing
  automatic rules. TimeDrops still requires a single swimming distance per heat;
  a mixed-distance swim heat must be resolved before generating that output package.
- Changing a whole heat's programme position shifts other heats. Membership stays
  intact. Swim lanes are preserved; run positions follow the normal save/reseed rule.
- Select **Combine** beside two or more programme rows and click **Combine** to
  pool/reseed only those heats, in either discipline. Equal distance is required.
  This manual request can cross age/gender boundaries. Running splits into balanced
  heats of at most 12; swimming uses pool capacity, slower/NT first, fastest last,
  with normal centre-out lanes. Unselected memberships remain unchanged. The new
  block occupies the earliest selected programme position and remains a draft until
  saved. Ordinary saves do not reorder heats by speed against manual programme order.
- **Add athlete to this event** stages a new entry with number-based historical seeds
  or NT, initially in a separate heat. **Remove from event** in either athlete table
  removes the entry from both disciplines on save. Historical results are retained.
  Duplicate-full-name warnings are nonblocking; athlete number remains the identity.
- Review and approve both disciplines before generating the output package.
  Assignment changes invalidate the old files: reapprove, regenerate and replace
  downloaded copies.
