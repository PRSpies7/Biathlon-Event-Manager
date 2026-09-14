# Current heat-generation rules for review

This describes the rules currently implemented, including the correction that
running positions start at 1. It is a description of the app's behaviour for
organiser review, not an official competition rulebook.

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

## 3. Initial heats

Create separate groups for age category, gender and distance first. Large running
groups are split into reasonably balanced heats. Large swimming groups put their
fastest athletes into full, same-age/gender heats, leaving any remainder in an
earlier, slower heat. Within each group, slower seeds and NT athletes are placed
in earlier heats; faster seeds are placed in later heats.

The optimisation pass merges whole incomplete heats. A small age/gender group,
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
2. Under 8 girls, then boys, if they have not joined an opening heat.
3. Under 9, Under 11.
4. Junior, Senior, Masters 40+, Masters 50+.
5. Under 13, Under 15, Under 17, Under 19.

**Swimming:**

1. Under 8 girls, then boys.
2. Masters 60+, 70+, 80+ and Special Needs: women, then men.
3. Under 9, Under 11, Under 13.
4. Junior, Senior, Masters 40+, Masters 50+.
5. Under 15, Under 17, Under 19.

When groups combine, compatible athletes move into an earlier incomplete heat.
The organiser can subsequently move an entire heat to any place in the programme.

## 5. Local league optimisation

**Running:** automatic heats have a maximum of 12 runners. Opening combinations
containing Masters 60+/70+/80+ or Special Needs target 10 runners. Same-gender
groups can combine up to 12 when that keeps a small group intact; the organiser
can adjust them afterward. Older Masters men and women remain separate when
their combined heat would exceed 10, but may combine at 10 or fewer.

Under 8 can run with Under 9, older Masters, or both, at the same 400 m distance.
Special Needs runners join older Masters where possible, preferably the same
gender. If a Masters heat is already full, some Masters runners may move into
the Special Needs heat so that they can run together within capacity. Special
Needs athletes in that group stay together.

Keep the same age category and gender first; then prefer same-gender compatible
categories, then mixed-gender compatible categories, with similar seeds as the
next preference. Opening combinations of 10 or fewer are preferred over larger
ones. Other automatic run heats can contain up to 12.

**Swimming:** one empty lane is acceptable. A heat with two or more empty lanes
can combine with another incomplete heat if the whole group fits. Prefer the
same age category and gender first, then same-gender compatible categories,
then mixed-gender compatible categories, and then similar seeds. Preserve full
same-age/gender fast heats; use the slower incomplete heats for mixing.

Both age and gender mixing are allowed. Same gender is a preference, not an
absolute restriction, so a mixed-gender heat can still be generated.

## 6. Interprovincial optimisation

- Running: consider combining only heats with six or fewer runners. Automatic
  capacity remains 12.
- Swimming: one or two empty lanes are acceptable. Consider combining only
  when at least three lanes are empty.
- Prefer the same gender, then compatible categories, then similar seeds.
- Mixing is allowed, but only among eligible incomplete heats of the same distance.

## 7. National / South African Championships

Keep age categories and genders separate. No automatic mixing. Incomplete heats
are acceptable. Automatic run capacity remains 12; swim capacity is the confirmed
pool lane count.

## 8. Which categories can combine?

Matching distance is always required. The current compatibility list permits:

- Different genders of the same category where the event type allows mixing.
- Masters 40+ with 50+.
- Masters 60+, 70+, 80+ with each other and with Special Needs.
- Under 8/9/11 with each other where their discipline distances match.
- Under 13/15 with each other where their distances match.
- Under 15/17/19 with each other.
- Under 19 with Junior/Senior, and Junior with Senior.
- Under 13 with Under 17 or Under 19, at lower preference and only at the same distance.
- Under 8/9 with Masters 60+/70+/80+ for the 400 m run only.
- At local meets, Special Needs with Under 8/9 for the 400 m run only.

Every athlete joining a heat must be compatible with every category already
in that heat. Compatibility does not automatically extend through another group.

The normal optimiser combines whole eligible incomplete heats, leaving full
heats and swim heats with an acceptable number of empty lanes intact. It never
splits a small group merely to fill spare lanes. If the whole group cannot fit,
the heats remain separate. Seed similarity breaks category/gender ties; after
that it favours the smaller compatible heat. The Special Needs run placement
described above is the exception that can redistribute a full Masters run heat.
The app does not perform a global search for the best possible programme.

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
- Moving a whole heat changes its programme position and shifts/renumbers other
  heats. It preserves the athletes and lane assignments within each heat.
- Reseed run starting positions numbers the existing run heats from 1 without
  changing membership; it replaces any manual run-position overrides.
- Review and approve both disciplines before generating the output package.
  Assignment changes invalidate the old files: reapprove, regenerate and replace
  downloaded copies.
