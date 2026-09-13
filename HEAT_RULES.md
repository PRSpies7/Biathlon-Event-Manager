# Current heat-generation rules for review

This describes the rules currently implemented, including the correction that
running positions start at 1. It is a description of the app's behaviour for
organiser review, not an official competition rulebook.

## 1. Distances

The defaults are the same for male and female athletes.

| Group | Running | Swimming |
| --- | --- | --- |
| Under 8 | 400 m | 25 m |
| Under 9, 10, 11 | 400 m | 50 m |
| Under 12, 13 | 800 m | 50 m |
| Under 15, 17, 19 | 800 m | 100 m |
| Junior, Senior, Masters 40+, Masters 50+ | 800 m | 100 m |
| Masters 60+, 70+, 80+ | 400 m | 50 m |
| Special Needs | 400 m | 50 m |

Explicit uploaded distances take precedence over these defaults. The organiser
can correct distances; a difference from the default is highlighted. Different
distances are never automatically combined in one heat.

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

Create separate groups for age category, gender and distance first. Split large
groups into heats, initially spreading the numbers as evenly as possible.
Within each group, slower seeds and NT athletes are placed in earlier heats;
faster seeds are placed in later heats. The optimisation pass can then change
the membership and occupancy of incomplete heats.

NT athletes stay within their age/gender structure initially. They are not all
collected into one unrelated NT group.

## 4. Programme sequence

This is the starting order, not an instruction to combine every listed group.
Women/girls come before men/boys within each category. The older Masters and
Special Needs block places all its female categories before its male categories.

**Running:**

1. Masters 60+, 70+, 80+ and Special Needs: women, then men.
2. Under 8 girls, then boys, if they have not joined an opening heat.
3. Under 9, Under 10 if entered, Under 11, Under 12 if entered.
4. Junior, Senior, Masters 40+, Masters 50+.
5. Under 13, Under 15, Under 17, Under 19.

**Swimming:**

1. Under 8 girls, then boys.
2. Masters 60+, 70+, 80+ and Special Needs: women, then men.
3. Under 9, Under 10 if entered, Under 11, Under 12 if entered, Under 13.
4. Junior, Senior, Masters 40+, Masters 50+.
5. Under 15, Under 17, Under 19.

When groups combine, compatible athletes move into an earlier incomplete heat.
The organiser can subsequently move an entire heat to any place in the programme.

## 5. Local league optimisation

**Running:** automatic heats have a maximum of 12 runners. Any automatically
created heat containing Masters 60+/70+/80+ or Special Needs has a maximum of 10.
Compatible Under 8/9 runners can join those opening heats. Same gender takes
priority for the opening heats, then category compatibility and similar seeds.
Other incomplete run heats prefer category compatibility, then same gender,
then similar seeds.

**Swimming:** one empty lane is acceptable. A heat with two or more empty lanes
can receive compatible athletes from another incomplete heat. Prefer category
compatibility, then same gender, then similar seeds.

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
- Under 8/9/10/11 with each other where their discipline distances match.
- Under 12/13/15 with each other where their distances match.
- Under 15/17/19 with each other.
- Under 19 with Junior/Senior, and Junior with Senior.
- Under 13 with Under 17 or Under 19, at lower preference and only at the same distance.
- Under 8/9 with Masters 60+/70+/80+ for the 400 m run only.
- At local meets, Special Needs with Under 8/9 for the 400 m run only.

Every athlete joining a heat must be compatible with every category already
in that heat. Compatibility does not automatically extend through another group.

The optimiser takes athletes only from other eligible incomplete heats, never
from full heats or swim heats with an acceptable number of empty lanes. It tries
to fill the earlier heat to capacity. Seed similarity breaks category/gender
ties; after that it favours the smaller donor heat. This can leave a small donor
heat, or remove it completely. It does not perform a global search for the best
possible programme.

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
- The table permits explicit manual position/lane and seed overrides.
- Manual run heats can exceed 12, with a notice. Swimming cannot exceed pool
  capacity, and duplicate positions/lanes are blocked.
- Moving a whole heat changes its programme position and shifts/renumbers other
  heats. It preserves the athletes and lane assignments within each heat.
- Reseed run starting positions numbers the existing run heats from 1 without
  changing membership; it replaces any manual run-position overrides.
- Review and approve both disciplines before generating the output package.
  Assignment changes invalidate the old files: reapprove, regenerate and replace
  downloaded copies.
