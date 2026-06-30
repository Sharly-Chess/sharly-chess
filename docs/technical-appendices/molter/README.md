# Molter Table Documentation

This directory documents the current Molter-table approach: **compact recipes
built offline and replayed by the application**.

The project no longer claims that a simple final constructive algorithm has been
found. The rules, validation model, quality metrics, and rebuild workflow are
explicit so that future research can improve the tables without changing the
Molter contract.

## Contents

| File | Purpose |
|------|---------|
| `molter-specification.md` | Standalone specification: hard rules, ideals, quality requirements, and a high-level overview of the recipe approach. |
| `molter-developer-guide.md` | Developer guide: runtime path, `.mrec` format, rebuild scripts, validation, and known limits. |
| `build_quality_summary.py` | Main quality-audit workbook for the recipe artifact: validation, timings, grades, I1, I1 prefix deficit, I2 L1, I3, I4, I5, exact/relaxed S5. By default it replays `src/data/pairings/resources/molter_recipes.mrec` and audits `N<=50`, `P=2,4,6,8,10,12`, `R<=14`. |
| `build_solver_recipe_suite.py` | Reproducible recipe-suite orchestrator. It runs deterministic passes, resumes without discarding completed work, merges the best results by metric priority, and writes a manifest. |
| `build_solver_recipes.py` | Low-level recipe build/replay tool. JSON is the readable resumable research state; the adjacent `.mrec` file is the compact runtime artifact. |
| `build_xlsx.py` | Builds display workbooks with in-sheet controls for team and floater highlighting. |

## Current Approach

The application loads `src/data/pairings/resources/molter_recipes.mrec`. This
file does not store every final pairing verbosely. It stores, for each covered
case, a compact schedule recipe plus one colour bit per game. Replay rebuilds
the table deterministically without a live solver or runtime search.

The app-visible Molter range is capped for quality:

- `N = 3..20` teams;
- `P = 2,4,6,8,10,12` players per team;
- `R = 1..13` rounds, where `R < N`.

The packed research artifact also contains recipes for `N = 21..25`. They stay
available for audit and future improvement, but the application does not expose
them because the current quality work is not good enough there.

If an exact requested shape is not covered by the app-visible range, the
application refuses the Molter table instead of improvising a result.

The underlying recipe collection currently covers:

- `N = 3..25` teams;
- `P = 2,4,6,8,10,12` players per team;
- `R = 1..13` rounds, where `R < N`.

## Hard Constraints

A table is **structurally valid** only if the verifier accepts every hard rule:

- **S1**: `P` is even and every round has `N*P/2` games.
- **S2**: every player plays exactly once per round.
- **S3**: teammates never play each other.
- **S4**: a player never faces the same opposing team twice.
- **S4b**: when a team has multiple boards in a round, they must not all target
  the same opposing team.
- **S5**: for each team, cumulative `White - Black` drift is at most `2`,
  returns to `0` after every two-round block, and returns to `0` at the final
  round.
- **S6a/S6b/S6c**: no floaters when `N` is even; for odd `N`, floaters only
  move between consecutive boards with the odd board descending; no player
  repeats the same floater role.
- **C1**: each player finishes colour-balanced, within one game when `R` is odd.
- **C2**: no player has three consecutive games with the same colour.
- **C3**: during the event, individual colour drift is at most `2`; at the final
  round it is at most `1`.

These rules are non-negotiable. A recipe that violates them is a failure even if
its ideal metrics look good.

## Ideals and Quality

The ideals are not optional in practice. They do not decide structural validity
on their own, but they decide whether a Molter table is **good quality**.

The `I` metrics are numbered in the priority order used to choose between valid
recipes:

1. **I1 and prefix coverage**: spread opponents as uniformly as possible, and
   make teams meet as many distinct opponent teams as possible in early rounds.
2. **I2 L1**: minimise `sum(abs(descending[t] - ascending[t]))`. `I2 = 0` is
   perfect; `I2 <= N-1` is good; `N-1 < I2 < 2(N-1)` needs review;
   `I2 >= 2(N-1)` should be avoided.
3. **I3**: equalise descending-floater counts across teams.
4. **I4**: limit repeated floater roles inside each round-pair when arithmetic
   permits it.
5. **I5**: spread a team's players evenly across opponents within each round.

Exact per-round S5 is kept when compatible with those priorities. Otherwise the
hard bounded S5 rule remains mandatory.

The quality workbook turns these signals into grades:

- **A**: valid, with no measured quality defect.
- **B**: valid, with only small ideal deviations.
- **C**: valid, but visibly weaker; review required.
- **D**: hard-valid, but not good enough to call the case solved.
- **FAIL**: generation or verification failed.

A **good Molter table** therefore requires full hard-rule validation and an A/B
grade. A C grade can be accepted only with documented reasoning or proof that a
better table is impossible. A D grade is a remaining research case, not a quality
success.

## Current Artifact Status

Current recipe snapshot:

- `1398/1398` covered recipes are structurally valid.
- The application quality gate exposes the `1008` recipes with `N <= 20`.
- Quality distribution: `A=360`, `B=902`, `C=33`, `D=103`, `FAIL=0`.
- A/B cases dominate up to roughly twenty teams.
- The serious remaining weaknesses are mostly larger-`N` I1/prefix cases,
  especially around `N = 21`, `N = 23`, and `N = 25`.

This work produces valid and generally good tables over the current range, but
it does **not** close the mathematical problem. Stronger CP-SAT, SAT, ILP, C++,
SageMath, or combinatorial constructors are welcome if they preserve the hard
rules and improve the quality vector.

## Useful Commands

```sh
# Main audit of the shipped artifact
python3 build_quality_summary.py molter_quality_summary.xlsx --workers 8 --recipe-file ../../../src/data/pairings/resources/molter_recipes.mrec

# Display workbook; use the per-sheet checkbox to highlight floaters in red
python3 build_xlsx.py molter_tables.xlsx --recipe-file ../../../src/data/pairings/resources/molter_recipes.mrec

# Rebuild a recipe collection, resuming by pass
python3 build_solver_recipe_suite.py --output .context/quality_grid_all_recipes.json

# Replay or inspect a low-level recipe file
python3 build_solver_recipes.py --replay .context/quality_grid_all_recipes.mrec
```

The `.xlsx` files are generated outputs. The runtime artifact is
`src/data/pairings/resources/molter_recipes.mrec`; the reproducible rebuild path
is `build_solver_recipe_suite.py` plus the builder sources.
