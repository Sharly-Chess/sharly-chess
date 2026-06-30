# Molter Tables — Specification and Quality Contract

This document defines what a Molter team-pairing table must satisfy, how table
quality is judged, and how the current Sharly implementation obtains its tables.
It is intentionally **not** a claim that we have found a final constructive
algorithm. The shipped implementation uses compact offline-built recipes, then
replays them deterministically at runtime.

The important distinction is:

- **Structural validity**: every hard rule in section 3 passes the verifier.
- **Molter-quality validity**: the table is structurally valid and its ideal
  metrics are good enough to be considered a satisfactory Molter table.
- **Reproduction**: exact byte-for-byte agreement with the current recipe
  artifact. Reproduction is useful for tests; it is not the mathematical
  definition of Molter.

An alternative implementation may use a solver, a different constructive
argument, an official hand table, or a native executable. It is acceptable if it
passes the hard verifier and matches or improves the quality vector described
below.

Notation:

- `N`: number of teams, `N >= 3`.
- `P`: players per team, even and `P >= 2`.
- `R`: number of regular rounds, `1 <= R < N`.
- Teams are indexed by `0..N-1`; display names are `A, B, C, ...`.
- Board 1 is the strongest player, board `P` the weakest.

## 1. Objects

**Player.** A pair `(team, board)` where `team in 0..N-1` and
`board in 1..P`.

**Uncoloured match.** An unordered pair of players from different teams.

**Coloured board.** An ordered pair `(white_player, black_player)`.

**Round.** A set of `N*P/2` coloured boards that partitions all players exactly
once.

**Table.** A sequence of `R` rounds.

**Floater.** For odd `N`, a match between adjacent board numbers `{i, i+1}` with
`i` odd. The player on the odd/lower board descends; the player on the even
higher board ascends. Even `N` tables must have no floaters.

**Round-pair.** Rounds are often analysed in blocks `(1,2)`, `(3,4)`, etc.; an
odd `R` leaves a final single round.

## 2. Validation Levels

The verifier distinguishes errors from notes.

- A **hard error** means the table is invalid and must not be emitted.
- A **quality note** means the table is structurally valid, but one ideal is not
  at its preferred value.

This split is deliberate: the app must never pair an invalid table, but the
research process also needs to see valid tables whose quality can still be
improved.

## 3. Hard Rules

A table is structurally valid if and only if all of these rules pass.

### S1 — Board Count

`P` is even and every round contains exactly `N*P/2` boards.

### S2 — One Game Per Player Per Round

Every player appears exactly once in each round. Over the table, all players
therefore play the same number of games.

### S3 — No Team-Mates

The two players on a board belong to different teams.

### S4 — No Repeated Opponent Team

No player meets two opponents from the same team. Since each player meets one
opponent team per round, this requires `R < N`.

Official rule-set overrides may mark a known impossible shape as a compromise,
but the default Molter recipe collection is strict.

### S4b — Per-Round Opponent Non-Degeneracy

When `N > 2`, if a team has several boards in one round, those boards must not
all be against the same opponent team. The round must be spread across at least
two opponent teams whenever that is possible.

### S5 — Team Colour Balance

For each team, cumulative `Whites - Blacks` drift:

- may never exceed `2` in absolute value;
- must return to `0` after every two-round block;
- must return to `0` at the final round.

Exact per-round team balance (`P/2` Whites and `P/2` Blacks for each team in
each round) is an ideal, not the hard S5 rule.

### S6a — Even-Team Floater Rule

If `N` is even, every match pairs equal board numbers. No floaters are allowed.

### S6b — Odd-Team Floater Legality

If `N` is odd:

- floaters may only join consecutive boards `{i, i+1}` with `i` odd;
- the player on the odd/lower board is the descending side;
- at most one descending floater occurs per odd board per round.

### S6c — No Repeated Floater Role

Across the table, no player descends more than once and no player ascends more
than once.

### C1 — Final Player Colour Balance

Over the full table, each player has equal White and Black counts when `R` is
even, or differs by one when `R` is odd.

### C2 — No Colour Triple

No player has the same colour in three consecutive rounds.

### C3 — Bounded Player Prefix Drift

After any non-final round, no player may have colour drift above `2` in absolute
value. After the final round, no player may drift above `1`, which is also C1.

Examples:

- `WWBB` is acceptable in a four-round event.
- `WBWWB` is acceptable in a five-round event.
- `BBB` is rejected by C2.
- `WWBWWW` is rejected because the intermediate drift becomes too large.

## 4. Ideals

The ideals are normative quality requirements applied **after** hard validity.
The `I` metrics are numbered in recipe-selection priority order: I1, I2, I3,
I4, I5. Exact per-round S5 is an additional named ideal, not an extra numbered
`I` metric.

When two valid candidates conflict, an implementation should not knowingly
worsen an earlier numbered criterion to improve a later one. Exact S5 is kept
when compatible with the numbered priorities.

### I1 — Opponent Uniformity and Prefix Coverage

The perfect target is that each team meets every other team equally often in
every round. This is exact when `(N-1)` divides `P`.

When exact per-round I1 is arithmetically impossible, short prefixes become the
critical target: after `r` rounds, each team should have met as many distinct
opponent teams as arithmetic permits, ideally `min(N-1, P*r)`.

The audit workbook reports:

- `I1`: cumulative opponent-count spread. `0` is perfect; `<=1` is the practical
  target.
- `I1 prefix deficit`: missing distinct opponents in the worst prefix. `0` is
  the target.

### I2 — Ascend/Descend Balance

For each team:

```text
signed_i2[team] = descending_floaters[team] - ascending_floaters[team]
```

Positive means the team was favoured by descending more often than ascending;
negative means the team was disadvantaged. The score used for comparison is the
L1 total:

```text
I2 = sum(abs(signed_i2[team]) for team in teams)
```

Bands:

- `I2 = 0`: perfect.
- `I2 <= N-1`: good.
- `N-1 < I2 < 2*(N-1)`: uncomfortable.
- `I2 >= 2*(N-1)`: avoid.

### I3 — Descending Floater Spread

Descending-floater counts should be as even across teams as arithmetic allows.
The metric is `max(descending_count) - min(descending_count)`.

### I4 — Floater Roles Per Round-Pair

In a round-pair, a team should descend at most once and ascend at most once when
that is arithmetically possible. This is exact only for some single-layer shapes;
once `P > N-1`, it can be impossible.

### I5 — Per-Round Opponent Spread

Within a round, a team's players should be spread evenly across opponent teams
rather than concentrated unnecessarily.

### Exact S5 — Per-Round Team Colour Balance

The preferred colour shape is `P/2` Whites and `P/2` Blacks for every team in
every round.

This is kept whenever it is compatible with stronger opponent/floater objectives.
If exact per-round S5 forces worse I1/prefix quality, the hard bounded S5 rule may
be used instead. The workbook reports this as `Exact S5 per round` or `S5
relaxed`.

## 5. Quality Requirement

The project uses two validities:

| Status | Meaning |
|--------|---------|
| Invalid | At least one hard rule S1-S6c or C1-C3 fails. Must never be emitted. |
| Structurally valid | All hard rules pass. Safe to pair, but quality may still be weak. |
| Molter-quality valid | Hard rules pass and the ideal metrics are good enough for an official-quality table. |

The quality workbook assigns grades:

| Grade | Meaning |
|-------|---------|
| A | Structurally valid; no measured quality penalty. |
| B | Structurally valid; only small ideal misses. |
| C | Structurally valid; visible ideal miss. Requires review or justification. |
| D | Structurally valid, but serious ideal miss. This is research debt, not a solved Molter case. |
| FAIL | Generation or verification failure. |

For a **good Molter table**, the target is A or B. A C table may be accepted only
with a documented reason, such as evidence that the loss is forced by a
higher-priority rule. A D table should not be described as high quality even when
it passes the hard verifier.

## 6. Current Implementation Approach

When pairing a Molter tournament, the app replays a packed resource:

```text
src/data/pairings/resources/molter_recipes.mrec
```

Each recipe case stores:

- `team_count`, `players_per_team`, `rounds`;
- a compact schedule description;
- one colour bit per board.

The recipe is not a dump of final printed pairings. It is a compact, deterministic
instruction stream. Runtime replay expands the schedule into uncoloured matches,
applies the colour bits, emits a `FixedPairingTable`, and lets the fixed-table
engine use that table.

The current schedule encodings are:

- `even_factor_rows`: rows of 1-factor indices for even `N`;
- `odd_cell_drops`: odd two-board cells described by factor offsets and dropped
  floater edges;
- `odd_cell_occurrences`: explicit odd cell choices, including factor, dropped
  edge, reverse phase and optional team shift.

Missing shapes are refused. If the exact `(N, P, R)` recipe is absent, the app
does not invent a table at runtime.

## 7. How Recipes Are Built

The recipe builders are offline research tools. They are deterministic and
resumable, but they are a portfolio of searches rather than a final mathematical
algorithm.

The broad workflow is:

1. Start from the current portable generator to get a valid baseline when
   possible.
2. Try alternative schedule families for weak cases, especially I1 and prefix
   failures.
3. Use CP-SAT/OR-Tools passes where useful to search rows, offsets, integrated
   schedule/colour choices and strict-S5 recolourings.
4. Verify every candidate against the hard Molter rules.
5. Keep only candidates that are not worse than the current best metric vector.
6. Merge pass outputs by priority metric.
7. Pack the winning cases into `.mrec`.

The merge priority follows the numbered `I` definitions:

```text
I1,
I1 prefix deficit,
total/vector I1 prefix deficit,
I2 L1,
I3,
I4,
I5,
S5 exactness
```

The JSON output is intentionally verbose because it is an audit and resume file.
The `.mrec` output is the compact runtime artifact.

## 8. Current Coverage and Limits

The runtime app exposes:

- `N = 3..20`;
- even `P = 2..12`;
- `R = 1..13`, where legal.

The current packed research artifact covers:

- `N = 3..25`;
- even `P = 2..12`;
- `R = 1..13`, where legal.

Current quality snapshot:

- `1398/1398` covered cases are structurally valid.
- `1008` covered cases with `N <= 20` are exposed by the runtime app.
- `A = 360`, `B = 902`, `C = 33`, `D = 103`, `FAIL = 0`.
- Serious D-grade cases are mostly larger-team I1/prefix coverage failures,
  concentrated from roughly `N = 19` onward and especially at `N = 21`, `23`,
  and `25`.

In practical terms: the current work gives high-quality tables up to about twenty
teams, with a few visible exceptions before that. Beyond that, more research is
needed. This may be better CP/SAT/ILP modelling, a stronger constructive
argument, better native search, or official table expertise.

## 9. Conformance

An implementation may target three levels.

### Structural Conformance

Every emitted table passes all hard rules S1-S6c and C1-C3.

### Quality Conformance

Every emitted table is structurally valid and reaches the best known metric
vector under the priority order in section 4. At minimum, it should not be worse
than the shipped recipe for the same `(N, P, R)` unless the loss is documented
and justified by a higher-priority constraint.

### Reproduction Conformance

The emitted table is exactly identical to the table replayed from the current
`.mrec` artifact for the same `(N, P, R)`.

Reproduction is useful for regression tests. Structural and quality conformance
are the real Molter contract.
