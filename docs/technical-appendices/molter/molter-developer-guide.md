# Molter Table Recipes — Developer Guide

This guide explains the current Molter implementation for maintainers. The key
point is architectural:

> The app does not solve or construct Molter tables at pairing time. It replays a
> packed recipe artifact and refuses unsupported shapes.

The hard rules and quality contract are defined in
[`molter-specification.md`](molter-specification.md). If this guide and the code
disagree, the code and verifier are the source of truth.

## 1. Source Files

| File | Role |
|------|------|
| `src/data/pairings/molter.py` | Molter pairing-system integration. Checks rule-set overrides, then asks for a packed recipe table. |
| `src/data/pairings/molter_recipes.py` | Runtime `.mrec` loader and deterministic recipe replay. |
| `src/data/pairings/molter_recipe_replay.py` | Small runtime-only schedule expansion helpers used by recipe replay. |
| `src/data/pairings/resources/molter_recipes.mrec` | Compact recipe artifact shipped with the app. |
| `src/data/pairings/fixed_table.py` | Generic fixed-table engine used after a recipe has produced a `FixedPairingTable`. |
| `src/data/pairings/molter_verifier.py` | Hard-rule verifier and quality notes. |
| `docs/technical-appendices/molter/build_grid_recipes.py` | Primary recipe builder: factor-grid schedules with decoupled colouring. |
| `docs/technical-appendices/molter/molter_recipe_generator.py` | Portable table builder used for baselines and recipe research. Not imported by the app. |
| `docs/technical-appendices/molter/build_solver_recipe_suite.py` | Reproducible offline recipe-builder orchestration for the older search portfolio. |
| `docs/technical-appendices/molter/build_solver_recipes.py` | Low-level recipe build, replay, packing, metrics and merge helpers. |
| `docs/technical-appendices/molter/build_quality_summary.py` | Audit workbook for validation, timing and quality grades. |
| `docs/technical-appendices/molter/build_xlsx.py` | Human-readable table workbooks. |

## 2. Runtime Path

At pairing time:

1. `MolterPairingSystem.get_table(N, P, tournament)` checks whether the rule set
   provides an official override for `(N, P)`.
2. If no override exists, it calls
   `get_molter_recipe_table(N, P, rounds=tournament.rounds)`.
3. `molter_recipes.py` loads `resources/molter_recipes.mrec`, finds the exact
   recipe, materializes uncoloured matches, applies colour bits and returns a
   `FixedPairingTable`.
4. `FixedTablePairingEngine` turns the table row for the requested round into
   concrete pairings.

Important behaviour:

- Unsupported shapes are reported as unavailable.
- If `(N, P)` is missing from the recipe file, the app returns no Molter table.
- If `(N, P)` is known but the exact `R` is missing, the recipe loader can return
  the maximum known recipe for that shape so the fixed-table layer can report a
  concrete round limit. It must not silently wrap a shorter table.
- Supported team counts come from the recipe file itself via
  `supported_molter_recipe_team_counts()`.

## 3. What a Recipe Stores

The `.mrec` file is compact binary data, not a verbose dump of all printed
pairings. It starts with a magic header (`MLTRCP`) and a packed version, then a
varint-encoded list of cases.

Each case contains:

- `team_count`;
- `players_per_team`;
- `rounds`;
- a schedule payload;
- `colour_bit_count`;
- packed colour bytes.

The current schedule kinds are:

| Kind | Meaning |
|------|---------|
| `even_factor_rows` | Even-team cases. Stores rows of one-factor indices. Replay expands them with `_even_matches_from_factor_rows`. |
| `odd_cell_drops` | Odd-team cases using offset rows and one dropped floater edge per `(block, factor)` cell. |
| `odd_cell_occurrences` | Odd-team cases using explicit cell occurrences: factor, dropped edge, reverse phase and optional team shift. This is larger than `odd_cell_drops` but still much smaller than storing final tables. |

Replay is deterministic:

1. Expand the schedule into uncoloured matches.
2. Read one colour bit per match.
3. If the bit is true, keep `(first, second)`; otherwise reverse it.
4. Emit the resulting coloured rounds through the normal `_emit` ordering.

Because colours are bits, the app does not need to solve C1/C2/C3 at runtime. The
artifact is verified by tests and by the quality workbook.

## 4. Hard Rules and Ideals in Code

The verifier is responsible for the hard contract:

- S1 board count.
- S2 every player exactly once per round.
- S3 no team-mates.
- S4 no repeated opponent team.
- S4b no per-round opponent collapse.
- S5 bounded team colour drift with return to zero after every two-round block
  and at the final round.
- S6a/S6b/S6c floater legality.
- C1 final player colour balance.
- C2 no colour triple.
- C3 bounded player prefix drift.

Quality metrics are computed by the workbook and recipe builders:

- `I1`: cumulative opponent-count spread, plus `I1 prefix deficit` for early
  distinct-opponent coverage. `0` ideal, `<=1` spread target.
- `I2`: `sum(abs(descending - ascending))` over teams.
- `I3`: descending-floater spread.
- `I4`: repeated floater roles inside round-pairs.
- `I5`: per-round opponent spread.
- `Exact S5`: whether every team has `P/2` Whites and `P/2` Blacks in every
  round.

The practical quality target for a good Molter table is grade A or B in
`build_quality_summary.py`. Grade C requires review. Grade D is structurally
valid but should be treated as an unsolved quality case.

## 5. Current Coverage and Quality

The app-visible Molter range matches the packed artifact:

- `N = 3..25`;
- even `P = 2..12`;
- every legal round count `R = 1..N-1`, including full round robins.

Latest validated snapshot:

- `1794/1794` covered cases pass hard validation and are exposed by the app.
- Quality grades: `A=384`, `B=1410`, `C=0`, `D=0`, `FAIL=0`.
- Every case reaches its arithmetic I1 lower bound with a zero prefix
  deficit. The B-grades are small ideal misses: mostly relaxed per-round
  colour balance (hard bounded S5 instead of exact) and minor I2/I3/I4 slack.

The grid builder is the maintained candidate source for the runtime artifact;
the older suite remains a valid challenger and still owns the best known
recipes for a minority of shapes.

## 6. Offline Recipe Build Workflow

The artifact is cumulative: every rebuild merges new candidates against the
current `.mrec`, and a candidate replaces an existing recipe only when it is
strictly better under the metric priority and passes the hard verifier. There
is therefore no required builder order — run any builder over any subset of
shapes and merge.

The primary candidate source is the grid builder:

```sh
# Rebuild candidates for the whole grid, or pass --case N,P,R for one shape
python3 docs/technical-appendices/molter/build_grid_recipes.py \
  --output .context/grid_recipes.json

# Merge against the shipped artifact and pack
python3 docs/technical-appendices/molter/build_solver_recipes.py \
  --merge-only --ignore-existing-output \
  --merge-input src/data/pairings/resources/molter_recipes.mrec \
  --merge-input .context/grid_recipes.json \
  --output .context/merged.json --packed-output .context/merged.mrec
```

The grid builder treats schedule and colour as independent problems:

1. **Schedule.** Both parities reduce to a symbol grid — one 1-factor per
   board (even `N`) or one one-odd 2-factor per board pair (odd `N`), per
   round. S4 only forbids repeating a factor in a column, so balanced loads
   give the `I1` optimum, fresh factors in early rows give a zero prefix
   deficit, and distinct factors per row give `I5 <= 1`. For odd `N` a small
   backtracking pass picks dropped edges (floater roles) per cell for
   S6c/I2/I3/I4, with a CP-SAT role polish for the stubborn shapes.
2. **Colour.** Rounds are coloured in two-round blocks. The union of a block's
   matchings is a set of even cycles; alternating colours around each cycle
   satisfies C1/C2/C3 and returns every team to balance at the block boundary.
   Per-cycle flips (then, if needed, a per-block CP-SAT that lets a few
   players carry a one-block colour debt) keep the odd-round team drift within
   the S5 bound. The last two blocks are solved together so the final block's
   constraints are planned for.

The older search portfolio (`build_solver_recipe_suite.py` over
`build_solver_recipes.py`) remains a valid candidate source and still wins on
a minority of small shapes — mostly exact per-round colour balance and some
two-round tables — so its recipes persist in the artifact.

The merge priority follows the numbered I definitions, with the I1 prefix
signals immediately after I1:

```text
I1
I1 prefix deficit
I1 prefix deficit total/vector
I2
I3
I4
I5
exact S5
```

A candidate that validates but worsens an earlier metric is rejected even if a
later metric improves.

The JSON is verbose by design: it is the resumable audit state. The adjacent
`.mrec` is the compact replay artifact. After promoting a new artifact, run the
tests and rebuild the audit workbook before committing.

## 7. Quality Workbook

Use `build_quality_summary.py` for broad review:

```sh
python3 docs/technical-appendices/molter/build_quality_summary.py \
  docs/technical-appendices/molter/molter_quality_summary.xlsx \
  --workers 8 \
  --recipe-file src/data/pairings/resources/molter_recipes.mrec
```

The workbook includes:

- dashboard totals;
- grade matrix by `N/P/R`;
- I1 matrix;
- prefix-deficit matrix;
- timing matrix;
- all row-level cases;
- cases to inspect;
- rollups by team count.

This workbook replaces the old split between summary, NPR and I1 diagnostics for
most decisions. Use `build_solver_recipes.py` directly only when investigating
or improving one recipe-builder pass.

## 8. Human-Readable Table Workbooks

Use `build_xlsx.py` for the tables themselves:

```sh
python3 docs/technical-appendices/molter/build_xlsx.py \
  docs/technical-appendices/molter/molter_tables.xlsx \
  --recipe-file src/data/pairings/resources/molter_recipes.mrec
```

The table workbook includes per-sheet controls: a team-letter selector and a
checkbox that colours floater matches red. It also includes the colour
transition tab. These files are generated artifacts, not sources of truth.

## 9. Testing

Run the recipe tests after changing the artifact or replay code. Run the
generator tests when changing the offline builder, generator helpers, or
baseline construction:

```sh
python3 -m pytest tests/unit/test_molter_recipes.py tests/unit/test_molter_recipe_generator.py
```

Useful focused checks:

- `iter_molter_recipe_tables()` materializes every packed recipe.
- `verify_molter_table(table)` must pass for every recipe table.
- The XLSX files should open as valid zip packages after regeneration.

Do not rely only on a visual workbook. The verifier is the hard-rule gate.

## 10. Extending Coverage

To add more cases:

1. Change the grid constants or command-line bounds in the recipe builder.
2. Run the suite into `.context`.
3. Compare quality against the previous artifact.
4. Promote only cases that validate and are not worse by the metric priority.
5. Copy the new `.mrec` to `src/data/pairings/resources/molter_recipes.mrec`.
6. Rebuild `molter_quality_summary.xlsx` and the human-readable workbooks.
7. Run tests.

If a shape is not in the recipe file, the app should continue to refuse it. That
keeps support limits explicit and avoids silent quality regressions.

## 11. Research Notes

Replay is fast; all remaining questions are offline. The central finding
behind the grid builder is that schedule quality and colour legality are
almost independent:

- Every valid schedule is hard-rule colourable per two-round block by cycle
  alternation, so I1/prefix quality never has to be traded away for
  colourability in general.
- The genuine coupling is narrow: bounding the odd-round team drift is a
  discrepancy problem over cycle flips, and it has real infeasibility pockets.
  At `R = 2` every player must alternate, drift is fixed entirely by the flip
  choice, and some factor pairings provably cannot stay within the bound —
  those shapes need colour-aware schedule selection, which the older builder
  provides.

Open questions worth pursuing:

- A rotational dropped-edge formula over a Hamiltonian (Walecki-style)
  2-factor decomposition could make the odd-`N` floater roles fully
  constructive. This needs a new schedule kind, because replay is tied to the
  shipped factorization.
- A characterization of the two-round colourability obstruction (which factor
  pairings admit flips within the drift bound).
- Exact per-round S5 together with optimal I1/prefix: the current artifact
  keeps exact S5 only where it costs nothing earlier in the priority order.

Any new approach is welcome if it keeps the verifier as the gate and improves
the quality vector.
