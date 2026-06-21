# Molter table generation — developer guide

This explains **how the Molter table generator works**, for developers who will
maintain it later. It assumes no special maths background: the few graph-theory
terms that appear are explained in plain words as we go.

> When this guide and the code disagree, the code and the verifier are the source
> of truth.

A language-neutral **specification** — enough to reproduce the tables in any
program — is in [`molter-specification.md`](molter-specification.md); this guide
is its code-level companion.

The three source files:

| File | Role |
|------|------|
| `src/data/pairings/molter_generator.py` | **Builds** a table for a given shape. |
| `src/data/pairings/molter_verifier.py` | **Checks** a table against the Molter rules. |
| `src/data/pairings/molter.py` | Wires Molter into the pairing-system framework. |

---

## 1. What problem are we solving?

A team event has **N teams**, each with **P players** (P is even). Players sit on
numbered **boards** 1…P; board 1 is the strongest player, board P the weakest.

Every round we must pair players across boards so that:

- everybody plays (no byes),
- you never play a team-mate,
- your colours stay balanced (as many Whites as Blacks),
- each team meets a fair spread of the other teams,
- nobody meets the same team twice across the event.

A **Molter table** is a precomputed schedule that satisfies all of this. The
generator builds one for any valid shape, and the verifier checks it before it is
used.

**Notation used throughout:** `N` = `team_count`, `P` = `players_per_team`,
`R` = number of regular rounds. Teams are letters `A, B, C…`; player `A1` is
team A's board-1 player.

---

## 2. How the code represents a table

```python
_Player = tuple[int, int]   # (team index 0-based, slot 0-based);  board = slot + 1
_Match  = tuple[_Player, _Player]   # an *uncoloured* board: who plays whom
_Board  = tuple[_Player, _Player]   # a *coloured* board: (white player, black player)
_Round  = list[_Board]
```

So a player is just "which team, which board". A **match** says *who plays whom*
but not the colours; a **board** adds the colours (the first element has White).
The public result is a `FixedPairingTable` whose `rounds` are tuples of
`TablePairing` (white team/board + black team/board).

---

## 3. The rules a table must satisfy

Everything the generator does is in service of these rules. They come in two kinds,
and the verifier (`molter_verifier.py`) enforces the split: **a table is only
emitted if every *hard* rule passes**; the nice-to-haves are reported as notes, not
errors. (Terms like *layer*, *floater* and *round-pair* are defined in the sections
that follow — skim past them for now.)

**Hard invariants (always true, every shape):**

- **S1** P is even; there are `N × P / 2` boards per round.
- **S2** every player plays exactly one game per round, the same number overall.
- **S3** team-mates are never paired.
- **S4** in strict tables, you never meet two opponents from the same team (this
  forces `R < N`). Rule sets may supply a marked compromise override for an
  otherwise impossible shape; the verifier then checks the stated compromise
  properties instead of strict S4.
- **S5** each team plays as many Whites as Blacks.
- **S6a/S6b/S6c** the floater rules: none at all for even N; for odd N a
  floater only joins two consecutive boards with the odd (stronger) board
  descending, at most one per odd board per round, and the floater role rotates so
  nobody floats the same way twice across the regular rounds.
- **C1 / C2 / C3** colour balance per player; never the same colour three rounds
  running; a repeat only across an even→odd boundary in strict tables. Marked
  compromise overrides still keep per-player colour balance and forbid triples,
  but may relax the boundary-repeat convention when that is part of the override.

**Ideals (only fully achievable on complete tables):**

- **I1** *(priority)* each team meets the others equally **every round** — exact
  when `N − 1` divides `P`.
- **I2** *(priority)* descending-floater counts as even across teams as arithmetic
  allows.
- **I3** each team has as many ascending as descending floaters.
- **I4** each round spreads a team's players evenly across opponents.
- **I5** at most one descending and one ascending floater per team per round-pair —
  exact only when `P = N − 1` (a single layer); impossible once `P > N − 1`.

### When each ideal holds

- The hard invariants (S1–S6c, C1–C3) hold for **every** strict shape — by
  construction, and confirmed by the verifier before a table is emitted. A rule
  set override can mark a table as a compromise; those are not emitted by the
  default generator.
- **I1** is reached on every round exactly when `N − 1` divides `P` (the table is
  whole layers); a final partial layer otherwise makes it best-effort.
- **I2** reaches its best spread (descending-floater counts differ by ≤ 1) on
  odd-`N` tables.
- **I5** holds only for a single layer (`P = N − 1`, odd `N`); once `P > N − 1` it
  is arithmetically impossible.
- **I3/I4** are not separate optimization targets in the current construction.
  I3 is mostly a consequence of round-pair reversal on regular paired rounds,
  while I4 follows I1 on full layers and becomes best-effort on partial layers.
  The verifier reports any remaining gaps as notes.
- Ideals that fall short are reported as notes — they never block a table.

---

## 4. The one big idea: teams first, colours second

The hard part is deciding, for each board in each round, **which two teams** the
players come from. Once you know "board 5 this round is `A` vs `D`", filling in
the exact players and the colours is mechanical.

So the generator works in two passes:

1. **Build the team schedule** — the uncoloured matches (`_Match`). This is where
   all the cleverness is.
2. **Colour it** — decide White/Black, with no searching.

Then it runs the verifier.

---

## 5. Building the team schedule

### 5.1 A "layer" = everyone-meets-everyone once

Picture each team as a dot. Draw a line between two dots when those teams play.
If **every team plays every other team exactly once**, you've drawn every possible
line — mathematicians call that a *complete graph* and write it `K_N`. It has
`N × (N−1) / 2` lines.

A **layer** is `N − 1` boards arranged so that, on each round, the teams playing
form exactly one such `K_N`. Why `N − 1` boards? Because that's how many boards it
takes for one team to meet all `N − 1` others. Building a layer differs by whether
N is even or odd:

**Even N — the circle method (`_one_factorization`).** This is the classic
round-robin trick: fix one team as a pivot and rotate the rest around it. Each
"rotation" is a **perfect matching** — a way to pair up *all* the teams at once
with nobody left over (possible because N is even). There are `N − 1` matchings,
and together they cover every team pair once. Board-slot `b` in round `r` simply
plays matching number `b + r` (mod N−1). Rotating the slot each round means a
fixed board meets a new team every round. No floaters here — both players on a
board share the same board number.

**Odd N — one dropped edge per two-board block.** With an odd number of teams you
*can't* pair everyone up on one board — there's always one team left over. That
leftover is handled by a **floater**: one player drops from an odd board down to
the next (even) board to find an opponent. The generator has two ways to build the
team graph behind that layout:

- **Full layers, checked sizes `N = 7..99`: prescribed one-odd 2-factorization.**
  A 2-factor is a set of cycles where every team has degree 2. The generator first
  fixes the floater edges by the affine rule
  `{r+b, r+b+m+1} mod N`, where `m = (N−1)/2`, `r` is the round-pair and `b` is the
  two-board block. Then `_one_odd_factorization` starts from the cyclic
  length-class 2-factorization, uses a deterministic recolouring pass to force
  those affine floater edges into the required factors, and runs a deterministic
  4-edge repair pass so the prescribed floater edge sits in the single odd
  component and all other components are even. `_complete_i1_one_odd_blocks` can
  then drop that edge and materialize the two-board block. This path makes I1
  exact and gives optimal single-layer I2 spread for every checked `N >= 7`.
- **Partial layers, checked sizes `N = 7..99`: one-odd factors with selected
  dropped edges.** The same repaired 2-factors are reused for partial layers. The
  generator first chooses a legal affine subset of logical blocks. If that subset
  already reaches the arithmetic lower bound for descending-floater spread, it is
  materialized directly. Otherwise a bounded deterministic repair search changes
  dropped edges inside the one-odd factors to try to reach that lower bound.
- **Small exceptions `N=3` and `N=5`: fixed one-odd factors.** `N=3` is below
  the general factor-search range. `N=5` cannot use the affine perfect-I2 target,
  but two fixed 5-cycles still fit the one-odd materializer. The planner is
  allowed to settle at I2 spread 2, which exhaustive search showed is the best
  possible while preserving S6c.

### 5.2 Stacking layers to reach P players

One layer fills `N − 1` boards. For `P` players we stack `k = P / (N − 1)` layers.
Each layer is its own full `K_N`, so each round ends up with `k` copies of
everyone-meets-everyone — meaning **each pair of teams meets exactly `k` times per
round**. That per-round balance is the priority ideal **I1**.

When `N − 1` doesn't divide `P` evenly, the leftover boards form a **partial
layer**. It still obeys every hard rule (distinct opponent each round, a legal
floater per block); the only thing it gives up is *perfectly even* spread — that
becomes "best effort". Full layers use a cached construction, so repeated
requests for the same size are free. Partial layers normally reuse the cached
one-odd factors. Unsupported odd sizes fail explicitly instead of running a slow
alternate search.

After each odd layer is built, the generator can rotate all team labels in that
layer. This preserves the pairings, future colour assignment, S6a/S6b/S6c, and
I1; it only changes which real teams receive that layer's descending-floater
incidences. A final deterministic rotation pass chooses layer shifts that
minimize I2. This prevents repeated small layers from charging the same teams
over and over — notably `N=3` and `N=7, P=14`.

These rotations also make the small repeated-layer cases match the same I2
standard as the larger construction: `N=3` reaches the arithmetic lower bound,
and `N=7` no longer needs a special exception. The only known small exception is
`N=5`, where S6c and perfect I2 conflict and spread 2 can be forced. For odd
`N >= 7`, current searches and constructions indicate that I2 spread `0` or `1`
is the right target; if a future implementation produces spread above 1 there, it
should be treated as a generator-quality issue unless proven unavoidable.

### 5.3 Why rounds are capped at N − 1

Within a layer, the cycle/matching assigned to each board **rotates** every
round-pair, so a fixed board sees a new opposing team each round. After `N − 1`
rounds you've used them all up — hence `1 ≤ R ≤ N − 1`. Any shorter prefix is
valid too, so a 2-round table is just the first two rounds of the full one.

---

## 6. Colouring — no search needed

The colour rule (invariants C1–C3): each player ends balanced, never plays the
same colour three rounds running, and may only **repeat** a colour across an
**even→odd** round boundary. Everywhere else colours must alternate.

That rule makes most colours *forced*:

- **Odd-numbered rounds are "free"** (rounds 1, 3, 5…). We colour them so that the
  *next* round's mandatory flip lands one White and one Black on every board. The
  trick is an **Eulerian orientation** (`_eulerian_colour` for odd N; via
  `_two_colour` for even N): walk along the loops of team-meetings and hand out
  colours so every team comes out with one White and one Black. "Eulerian" just
  means we follow the edges of each loop in order — no choices, fully
  deterministic (always start at the lowest-numbered team, take the
  lowest-numbered edge).
- **Even-numbered rounds are forced** (`_flip_colour`): every player takes the
  opposite of its previous colour.

A round-pair (one free + one flipped) leaves each player balanced. If `R` is odd,
the final free round has no partner to flip with, so it is coloured Eulerian on
its own — which is self-balancing because every team plays an even number `P` of
games.

---

## 7. Keeping floaters fair (odd N only)

For odd N the floater choice is the only place where S6a/S6b/S6c and I2 can
conflict. The reference method uses fixed one-odd factors for `N=3` and `N=5`,
and searched/repaired one-odd factors for checked sizes `N = 7..99`.

### Full layers: affine floaters plus one-odd factors

For a full layer (`P` contributes exactly `N−1` boards), the preferred path uses
the affine floater edge:

```text
floater(r,b) = {r+b, r+b+m+1} mod N, where m = (N−1)/2
```

In one round-pair, those `m` edges are vertex-disjoint, so exactly one team is
omitted and the others float once. Over the full schedule, the omitted team
rotates through the field and descending-floater incidence differs by at most one
for every checked `N >= 7`.

Those prescribed floater edges are then embedded into a 2-factorization of `K_N`:

1. `_one_odd_initial_factors` starts from the cyclic length-class
   2-factorization of `K_N`.
2. It pins every prescribed affine floater edge to its required factor, then
   recolours only non-prescribed edges. The score is the total deviation from
   degree 2 over all `(factor, team)` pairs, so score 0 means every factor is a
   spanning 2-regular graph and every team-pair edge appears exactly once.
3. `_one_odd_repair_factors` applies deterministic 4-edge switches between
   factors until each factor can be laid out across two boards: the prescribed
   floater edges are in one odd component, and every other component has even
   size.
4. `_one_odd_cell_matches` drops the prescribed edge for a cell. The remaining
   odd path and even cycles alternate across the adjacent boards, giving legal
   floaters without repeating a floater role.

This is why the former hard cases such as `N=17`, `N=21` and `N=49` are fast
without embedded grid constants.

`N=5` is the small exception: exhaustive search showed S6c and perfect I2 are
mutually exclusive there, so the hard no-repeat floater rule wins and I2 spread
is 2. It still uses the one-odd materializer, with two fixed 5-cycle factors.

### Worked odd example: N=5, P=4, first round-pair

This is the smallest useful example because `N=5` gives `m=(N−1)/2=2`, so one
full layer has two adjacent board blocks: boards `1/2` and boards `3/4`.

For round-pair `r=0`, the affine floater edge for block `b` is:

```text
floater(r,b) = {r+b, r+b+m+1} mod N
```

So the two dropped edges are:

```text
b=0: {0, 3}  -> teams A and D
b=1: {1, 4}  -> teams B and E
```

They are disjoint, so the round-pair has legal odd-team floaters: four teams
float once and team `C` is omitted from floating in that pair.

The fixed `N=5` factors are:

```text
factor 0 = (0-3, 0-4, 1-2, 1-3, 2-4)
factor 1 = (0-1, 0-2, 1-4, 2-3, 3-4)
```

For block `b=0`, `factor_index = (r+b) mod m = 0`, and the dropped edge is
`0-3`. Removing `0-3` from factor 0 leaves the path:

```text
0 - 4 - 2 - 1 - 3
```

`_one_odd_cell_matches` places that path across boards 1 and 2:

```text
floater:  D1 vs A2   (D descends from board 1, A ascends from board 2)
board 1:  A1 vs E1
board 1:  C1 vs B1
board 2:  E2 vs C2
board 2:  B2 vs D2
```

For block `b=1`, factor 1 drops edge `1-4`; that fills boards 3 and 4 in the
same way. The second round of the pair reuses the same dropped edges with the
path reversed, so the floater direction flips and each player gets the other
incident edge of the same factor.

The important mechanics visible in this tiny case are the same for larger odd
`N`: affine dropped edges make the round-pair floaters disjoint, each block uses
a factor whose odd component contains the dropped edge, and the remaining path
alternates across the adjacent boards.

### Why the team schedule works

The construction is designed so each local fact maps directly to one Molter rule:

- **Everyone plays exactly once (S2).** In an even layer, each board slot is a
  perfect matching, so every team appears once on that board. In an odd two-board
  block, dropping one factor edge turns the odd component into a path; the path
  alternates between the odd and even board, and the dropped edge becomes the
  floater. The result covers every team once on each of the two board numbers,
  with the two endpoint players used in the floater instead of a same-board game.
- **No team-mates, and no repeated opponent team (S3/S4).** Factors contain only
  edges between different teams. Across a full set of factors, every team-pair
  edge of `K_N` appears exactly once. A round-pair gives a player the two incident
  edges from one factor; the next round-pair rotates to another factor. Since the
  factors partition `K_N`, a player cannot meet the same opposing team twice
  before the `N−1` round cap.
- **Legal floaters (S6b).** A dropped edge always belongs to one adjacent
  two-board block. `_one_odd_cell_matches` always places one endpoint on the odd
  board and the other on the even board, with the odd-board endpoint descending.
  The planner also requires the dropped edges in a round-pair to be
  vertex-disjoint, so a round cannot ask the same team to float twice.
- **No repeated floater role (S6c).** For a fixed two-board block, the dropped
  edges used across round-pairs are vertex-disjoint. Therefore a team can appear
  as a floater endpoint for that player index at most once; the second round in a
  pair reverses direction, so each endpoint gets one descending and one ascending
  role, not repeated roles.
- **Per-round I1 on full layers.** A full odd layer has `m=(N−1)/2` blocks, and
  round `r` uses factor `(r+b) mod m` on block `b`. That permutation uses each
  factor exactly once in the round; because the factors partition `K_N`, every
  team-pair appears exactly once. Even layers have the same property with
  one-factor matchings.
- **I2 balancing does not disturb legality.** Final layer rotations are team-name
  automorphisms: they relabel every team in the layer by the same offset. That
  cannot create team-mates, repeated opponents, illegal floaters, or colour
  conflicts; it only changes which real teams receive that layer's descending
  floater counts.

### Partial layers: affine subsets plus bounded repair

For a partial layer, only `block_count < m` two-board blocks are used. The
generator first scores the affine logical block offsets by their actual
descending-floater contribution over `R` rounds, greedily selects offsets, and
applies deterministic local swaps. `_one_odd_affine_partial_plan` materializes
that plan immediately if the final descending counts hit the arithmetic lower
bound: spread 0 when `block_count × R` is divisible by `N`, otherwise spread 1.

When the affine subset is legal but one count away from the lower bound,
`_one_odd_partial_plan` tries a bounded exact repair. It keeps the same one-odd
factors, but each used cell may drop any edge in that factor's odd component.
The hard constraints are:

- **Each round-pair:** selected dropped edges across the used blocks are
  vertex-disjoint, so odd-team floaters are legal (S6b).
- **Each block:** selected dropped edges across round-pairs are vertex-disjoint,
  so no board repeats a floater team (S6c).
- **Descending counts:** the search first tries only the arithmetic lower-bound
  spread. It uses deterministic hash tie-break passes and a per-pass node cap.

For long/high-density partial schedules where exact repair would be slow, the
generator uses the fast legal affine subset. Those cases are valid and
deterministic but may have I2 spread 2 rather than the lower-bound spread 1.

## 8. Requested Rounds

`generate_molter_table` emits exactly the requested regular rounds. For normal
tournament generation the Molter pairing system passes the event's actual round
count to `generate_molter_table`, so a requested count such as 1, 3, 5, ... is a
real table whenever `R < N`. A one-round event is therefore just round 1 of a
valid one-round Molter table, already colour-balanced by construction.

---

## 9. The code path, end to end

`generate_molter_table(team_count, players_per_team, rounds=None)`:

1. **Validate**: `P` even, `N ≥ 3`, and `1 ≤ R ≤ N − 1`. `rounds` defaults via
   `default_molter_rounds` (odd counts 5 and 7 run "complete" = `N − 1` rounds;
   everything else defaults to 2). Bad input raises `MolterGenerationError`.
2. **Build matches** then **colour**, by parity:
   - odd N → `_complete_i1_matches` → `_colour_complete_i1_matches`
   - even N → `_complete_i1_even_matches` → `_colour_complete_i1_even_matches`
3. **Render** each round with `_emit` (sorts boards: all board-1 games first, a
   block's floater grouped with its lower board).
4. **Verify (opt-in).** When `_VERIFY_GENERATED_TABLES` is set, run
   `verify_molter_table` and raise `MolterGenerationError` on any hard-rule
   violation. It's **off by default** — the construction is trusted in production;
   turn it on when changing the algorithm or run the verifier from tests.

Results are `@lru_cache`d, so repeated requests for the same shape are free.

| Want to… | Function |
|----------|----------|
| Generate a table | `generate_molter_table` |
| Default round count | `default_molter_rounds` |
| Even-N team schedule | `_one_factorization`, `_complete_i1_even_matches` |
| Odd-N full-layer team schedule | `_one_odd_factorization`, `_complete_i1_one_odd_blocks`, `_complete_i1_matches` |
| Odd-N partial schedule | `_one_odd_affine_partial_plan`, `_one_odd_partial_plan`, `_complete_i1_one_odd_plan_blocks` |
| Full-layer floater edges / I2 | `_affine_floater_edge`, `_layer_descending_incidence`, `_optimise_layer_shifts` |
| Partial floater edges | `_one_odd_affine_partial_plan`, `_one_odd_partial_plan` |
| Colour a free round | `_eulerian_colour`, `_two_colour` |
| Colour a forced round | `_flip_colour` |

### From a table to round pairings (runtime)

When the event is known, `MolterPairingSystem.get_table` asks for
`generate_molter_table(N, P, rounds=tournament.rounds)`, so odd round counts are
generated directly whenever the generator supports them.

If a rule set ships an official override, that override is consulted first. This
is how the FFE cup `3 teams × 4 players × 3 rounds` table is allowed: it is
impossible under strict S4, so it is marked `is_compromise=True` and verified with
the compromise checks instead of being emitted by the default generator.

A generated `FixedPairingTable` is then turned into a round's actual pairings by
the fixed-table engine, via
`FixedPairingTable.round_pairings(round_index, total_rounds)` (in
`fixed_table.py`). It returns `rounds[(round_index − 1) % regular_round_count]`;
the Molter pairing system asks for a table with the event's own round count, so
standard Molter tournaments do not need a separate terminal round.

---

## 10. Worked examples

### Generate and read a table

```python
from data.pairings.molter_generator import generate_molter_table

table = generate_molter_table(team_count=3, players_per_team=4)  # default rounds
for round_number, rnd in enumerate(table.rounds, start=1):
    print(f"Round {round_number}")
    for board in rnd:
        print(f"  {board.white_team}{board.white_index} (W)"
              f" – {board.black_team}{board.black_index} (B)")
```

### A complete odd table — 3 teams, 4 players

`generate_molter_table(3, 4)` gives 2 rounds. Each round
has `N × P / 2 = 6` games, written `white – black`:

```
Round 1:  B1–C1   A1–B2   C2–A2   A3–C3   C4–B3   B4–A4
Round 2:  C1–A1   A2–B1   B2–C2   B3–A3   C3–B4   A4–C4
```

What to notice:

- **Six games per round** (S1: `N × P / 2`), and **no game pairs team-mates** — the
  two letters always differ (S3).
- **`A1–B2` and `C4–B3` are floaters.** Their two board numbers differ (a board-1
  player meets a board-2 player). With an odd team count you can't pair every board
  straight across, so the stronger (lower) board drops to its neighbour — that's
  the floater, and it's why nobody sits out (S6b).
- **The two layers are visible.** `P / (N−1) = 4 / 2 = 2` layers: boards 1–2 form
  one everyone-meets-everyone block (`B1–C1`, `A1–B2`, `C2–A2`), boards 3–4 the
  other (`A3–C3`, `C4–B3`, `B4–A4`).
- **Colours alternate.** A1 has White in round 1 (`A1–B2`) and Black in round 2
  (`C1–A1`) (C1/C3).

### The FFE three-team, three-round override

`generate_molter_table(3, 4, rounds=3)` is rejected by the default generator
because it asks for as many rounds as there are teams. Strict S4 is then
impossible: each player has only two opposing teams, so over three games one
opponent team must repeat.

The FFE cup rule set supplies an explicit `3×4×3` override marked
`is_compromise=True`. That table makes the forced repeat as harmless as possible:

```
Round 1:  A1–B1   A2–C1   B2–C2   C3–B3   C4–A3   B4–A4
Round 2:  B1–C1   B2–A1   C2–A2   A3–C3   A4–B3   C4–B4
Round 3:  C1–A1   C2–B1   A2–B2   B3–A3   B4–C3   A4–C4
```

What is still true:

- every round has two `AB`, two `AC`, and two `BC` games;
- every player repeats one opponent team exactly once (`2/1` split);
- no player meets the same individual opponent twice;
- floaters stay between adjacent boards only;
- each player gets either two Whites and one Black, or one White and two Blacks,
  with no three identical colours in a row.

### No floaters with an even team count — 4 teams, 4 players

```
Round 1:  A1–D1   B1–C1   A2–C2   D2–B2   A3–B3   C3–D3   A4–D4   B4–C4
```

Every game pairs **equal board numbers** (`A1–D1`, `B1–C1`, `A2–C2`, …): with an
even team count every board pairs straight across — no floaters at all (S6a). That
is the whole reason even and odd team counts take different construction paths.

---

## 11. Determinism, portability, performance

- **Deterministic and portable.** In this implementation, `(N, P, R)` defines
  exactly one table; there is no external solver and no user-visible seed. The
  full-odd path uses a small fixed pseudo-random stream only for tie-breaks in
  recolouring/repair; it is implemented in the generator and can be ported
  directly.
- **Validation should be the acceptance criterion.** This Python generator is the
  portable reference implementation, but its exact byte output should not be
  treated as the definition of Molter validity. The proposal is that a table
  generated by another implementation should be acceptable if it passes the
  verifier's hard invariants and respects the declared ideal priorities (I1
  before I2). A C++, SAT, CP, ILP, or otherwise specialized library may produce
  different valid tables, and may do so faster because it can propagate
  constraints in native code or use a stronger search engine. The intended
  acceptance test is the validated table, not the internal construction path.
- **Fast.** Even tables and many partial tables are still almost pure arithmetic.
  The full-odd path avoids the former large floater-grid CSP: on the 2026-06-20
  local factorization probe, every odd `N=53..99` succeeded; `N=69` built its
  reusable factors in about 2.4s. Partial odd tables use the same one-odd
  factors; bounded repair and layer rotation reach lower-bound I2 on many
  shorter/smaller partial cases, and high-round cases stay fast with legal
  spread-2 affine subsets when exact repair would be too expensive. The repair pass keeps
  per-factor scores incrementally, so only the two factors touched by a candidate
  swap are rescored; this avoids the former cold-start spikes in larger odd
  factorization experiments.

---

## 12. Extending it

- **New / changed rules** → edit `molter_verifier.py`. Keep the hard/soft split:
  hard rules `report.errors.append(...)`, ideals `report.notes.append(...)`.
- **Default round counts** → `default_molter_rounds`.
- **An official federation table for a specific size** → don't touch the generator.
  A rule set returns it from `molter_table_overrides()`, and
  `MolterPairingSystem.get_table` (in `molter.py`) prefers an override before
  falling back to the generator. That hook is the single extension point left to
  downstream consumers.
