# Molter table — formal specification

This document is a **formal, language-neutral specification** of the Molter
team-pairing table: the combinatorial objects it is built from, the invariants it
must satisfy, and the mathematical construction that produces one. It is written
for a reader who wants to *understand and validate* the method, not to transcribe
code.

Two notions of conformance are defined (§11):

- **Validity** — the actual contract. A table is *valid* if it satisfies every
  hard invariant of §3. Validity is independent of how the table was produced;
  any method — the construction below, a constraint solver, a hand table — that
  yields a table passing §3 is acceptable.
- **Reproduction** — exact agreement with the **reference implementation**. The
  construction of §§5–9 fixes a unique table for each input `(N, P, R)`, but it
  leaves a handful of choices (which factorisation, how internal ties are broken)
  to a *canonical deterministic rule*. Spelling that rule out in prose would not
  add mathematical content, so it is delegated: the script
  [`molter_standalone.py`](molter_standalone.py) in this folder **is** the
  canonical reference, and a table *reproduces* the reference iff it equals that
  script's output for the same `(N, P, R)`. The script is deterministic in
  `(N, P, R)` alone — there is no external seed.

Notation. `N` = number of teams, `P` = players per team (`P` even, `P ≥ 2`),
`R` = number of regular rounds. `ℤ_N = {0, …, N−1}`; arithmetic on team indices
is modulo `N` with non-negative residues. Set `m = (N−1)/2` when `N` is odd.

---

## 1. Objects

**Teams.** `ℤ_N`. The display letter of team `t` is the `(t+1)`-th letter
`A, B, C, …` (for `t ≥ 26`, the Unicode character after `Z`, etc.).

**Boards.** Each team fields `P` players on boards `1, …, P` (board 1 strongest).
A **player** is a pair `(t, i) ∈ ℤ_N × {1, …, P}`. Write `P = ℤ_N × {1, …, P}` for
the set of all `N·P` players.

**Match.** An unordered pair of players `{(t, i), (t′, j)}` with `t ≠ t′`. It says
*who plays whom* on one board, without colours.

**Board (coloured).** An ordered pair `(w, b)` of players; `w` has White, `b` has
Black.

**Round.** A set of `N·P/2` coloured boards whose underlying matches partition
`P` (every player appears on exactly one board). A **table** is a sequence
`(ρ_1, …, ρ_R)` of rounds.

**Layer.** A block of `N−1` consecutive boards (board slots) on which, in each
round, the *teams* that meet form a complete graph `K_N`: every team meets every
other exactly once. A layer accounts for `N−1` of a team's `P` players, so a table
uses `⌈P/(N−1)⌉` layers, the last possibly partial.

**Floater (odd `N` only).** A board whose two players have *different* board
numbers, necessarily consecutive `{i, i+1}` with `i` odd. The player on the odd
(lower, stronger) board **descends**; the player on the even board **ascends**.
A floater is forced exactly when `N` is odd: an odd number of teams cannot be
paired across equal boards.

**Round-pair.** Rounds are grouped two at a time: round-pair `p` is the pair
`(ρ_{2p+1}, ρ_{2p+2})`. The construction and the colouring both operate per
round-pair; an odd `R` leaves one unpaired final round.

**Descending count.** For team `t`, `d_t` is the number of rounds in which one of
`t`’s players is the descending side of a floater. The **descending spread** is
`max_t d_t − min_t d_t`.

---

## 2. The shape of the construction

The table is built in two independent passes, mirroring the structure of the
invariants:

1. **Team schedule (§§5–7).** Choose, for every board of every round, the
   unordered match — *which two teams meet, on which board numbers*. All the
   combinatorial work is here.
2. **Colouring (§8).** Orient each match into `(White, Black)`. This needs no
   search.

Both passes are deterministic functions of `(N, P, R)` (see §10). The top-level
map is

```
generate(N, P, R):
    require P even, P ≥ 2, N ≥ 3, 1 ≤ R ≤ N − 1
    S ← team_schedule(N, P, R)            # §§5–7 — a sequence of R rounds of matches
    return [ colour(S, p) for each round ]  # §8
```

`R` defaults by convention when unspecified (`R = N−1` for `N ∈ {5, 7}`, otherwise
`R = min(2, N−1)`); any `1 ≤ R ≤ N−1` is admissible (§9).

---

## 3. Hard invariants

A table is **valid** iff it satisfies all of the following. Each is a finite
property, checkable directly on the emitted rounds.

- **S1 (board count).** `P` is even and every round has exactly `N·P/2` boards.
- **S2 (one game per round).** In each round every player appears on exactly one
  board, and every player plays the same number of games over the table.
- **S3 (no team-mates).** The two players of any board belong to different teams.
- **S4 (no repeated opponent team).** No player meets two opponents from the same
  team. Since a player meets one opponent team per round and there are `N−1`
  others, this forces `R < N`.
- **S5 (team colour balance).** In every round each team has as many players with
  White as with Black. (Possible because every team plays an even number of
  boards per round.)
- **S6a (even `N`: no floaters).** If `N` is even, every board pairs equal board
  numbers.
- **S6b (odd `N`: legal floaters).** If `N` is odd, a floater joins only
  consecutive boards `{i, i+1}` with `i` odd, with the odd board descending; at
  most one descending floater occurs per odd board per round.
- **S6c (no repeated floater role).** Over the `R` rounds no player descends more
  than once, and none ascends more than once.
- **C1 (player colour balance).** Over the `R` rounds each player has equal White
  and Black counts when `R` is even, differing by one when `R` is odd.
- **C2 (no colour triple).** No player has the same colour in three consecutive
  rounds.
- **C3 (repeat only even→odd).** A player may repeat a colour from round `r` to
  `r+1` only when `r` is even (1-based); every other adjacent pair of rounds
  alternates that player's colour.

---

## 4. Ideals

These are graded objectives, not requirements; the construction attains them
under the stated conditions and otherwise approaches them. A valid table never
fails to be emitted because an ideal is missed; the priority order is **I1 before
I2**.

- **I1 (opponent uniformity).** In every round each team meets every other team
  equally often. Attained exactly iff `(N−1) ∣ P` (the table is whole layers).
  When `(N−1) ∤ P`, the construction instead maximises *prefix coverage*: after
  `r` rounds each team has met `min(N−1, P·r)` distinct opponent teams whenever
  that is arithmetically possible.
- **I2 (floater balance).** The descending spread (§1) is as small as the
  arithmetic allows — `≤ 1` for a single full odd layer with `N ≥ 7`. The lone
  exception is `N = 5`, where I2 and S6c cannot both be perfect and the minimum
  spread is `2`.
- **I3 (ascend/descend balance).** Each team descends as often as it ascends.
- **I4 (per-round spread).** Within a round a team's players are spread evenly
  across opponents.
- **I5 (single floater per role per round-pair).** Each team descends at most once
  and ascends at most once per round-pair. Attainable only for a single layer
  (`P = N−1`); arithmetically impossible once `P > N−1`.

I3 and I4 are consequences of the round-pair structure and of I1 rather than
separate optimisation targets.

---

## 5. Decomposing `K_N` into layers

A layer realises one `K_N` per round. Its construction depends on the parity of
`N`.

### 5.1 Even `N` — a 1-factorisation (circle method)

When `N` is even, `K_N` decomposes into `N−1` **perfect matchings** (1-factors)
`F_0, …, F_{N−2}` whose edge sets partition the `N(N−1)/2` team pairs. With team
`N−1` as pivot and the others on a ring of size `N−1`:

```
F_b = { {N−1, b} } ∪ { { (b+i) mod (N−1), (b−i) mod (N−1) } : 1 ≤ i ≤ N/2 − 1 }.
```

Each `F_b` is a perfect matching (no team omitted), so a board slot assigned `F_b`
pairs equal board numbers — **no floaters (S6a)**.

### 5.2 Odd `N` — a one-odd 2-factorisation

When `N` is odd no perfect matching exists, so the layer is built from
**2-factors**. A *one-odd 2-factorisation* is a partition of the edges of `K_N`
into `m = (N−1)/2` spanning subgraphs `G_0, …, G_{m−1}`, each **2-regular** (every
team has degree 2, so each `G_h` is a union of cycles), with two further
properties tied to the *floater edges* defined next.

**Affine floater edge.** For round-pair `p` and block `b`,

```
e(p, b) = { (p + b) mod N , (p + b + m + 1) mod N }.
```

Within one round-pair the `m` edges `e(p, 0), …, e(p, m−1)` are vertex-disjoint
(they form a near-perfect matching of `ℤ_N` omitting exactly one team), so each
round-pair floats `N−1` teams once and omits one; the omitted team rotates with
`p`. This rotation is what makes the descending spread small (I2).

**Prescribed edges.** Block `b` in round-pair `p` uses factor
`h = (p + b) mod m`. Collecting the floater edges that fall to each factor gives,
for every `h`, a set `E_h` of *prescribed edges* that `G_h` must contain.

**Materialisability.** `G_h` must be laid out across two adjacent boards by
*dropping* its prescribed edge (§6.2). This is possible exactly when the
prescribed edges of `G_h` lie in a single **odd-length** cycle of `G_h`, and every
other cycle of `G_h` has even length. A one-odd 2-factorisation is required to be
materialisable for every factor.

**Existence.** A materialisable one-odd 2-factorisation exists for every checked
odd `7 ≤ N ≤ 99`; the reference implementation finds one by a deterministic search
(start from the length-class 2-factorisation, pin the prescribed edges, repair the
component structure by local edge switches). `N = 3` and `N = 5` use fixed factors
(`N = 5` cannot reach perfect I2 and is allowed descending spread `2`). An odd `N`
for which no materialisable factorisation is known is rejected outright — there is
no silent fallback. The *existence* is what matters here; the canonical choice
among admissible factorisations is fixed by the reference (§10).

### 5.3 Materialising a 2-factor across two boards

Let `G_h` have prescribed edge `ε` lying in its odd cycle `C`. Deleting `ε` from
`C` turns the cycle into a **path** `v_0 — v_1 — … — v_k` (with `{v_0, v_k} = ε`).
Place this path across the block's two board numbers — odd board `2(o+b)+1` say,
and even board `2(o+b)+2`, where `o` is the layer's board offset:

- the **floater** is the board `{(v_k, odd), (v_0, even)}` — the dropped edge’s
  endpoints, the odd-board player descending;
- consecutive path edges alternate between the odd board and the even board, so
  every team on the path appears once on each board number.

Every other (even) cycle of `G_h` is laid "straight across": its teams alternate
between the two boards with no floater. The result is a legal two-board block in
which each team appears once on each board (S2), the only cross-board pairing is
the single floater (S6b), and the floater edge is `ε`.

In the **second** round of the round-pair the same block reuses the same dropped
edge with the path **reversed**; this swaps which endpoint descends, so a team
that descended in the free round ascends in the flip round.

---

## 6. Assembling the schedule

For `P` players a layer covers `N−1` board numbers, so there are
`k = ⌊P/(N−1)⌋` **full** layers and, when `(N−1) ∤ P`, one **partial** layer of
the remaining `P − k(N−1)` boards.

### 6.1 Full layers

Per round-pair `p`, block `b` of a full layer uses factor `h = (p + b) mod m`
(odd `N`) with dropped edge `e(p, b)`, or 1-factor `F_{(b+r) mod (N−1)}` in round
`r` (even `N`). Because the factor index rotates with the round, a fixed board
meets a new opponent team every round, and across the `m` (resp. `N−1`) blocks of
a round every team pair appears exactly once — i.e. **per-round I1**. Stacking `k`
full layers gives `k` copies of `K_N` per round, so each team pair meets exactly
`k` times per round.

### 6.2 Partial layer, odd `N` — spread offsets

A partial odd layer has `c < m` blocks. To make early prefixes cover opponents
fast (the I1 priority), the blocks are spread through the factor list rather than
packed together. With

```
offset(b) = ⌊ b·m / c ⌋ ,        factor(r, b) = ( r + offset(b) ) mod m ,
```

block `b` advances by one factor each round, and the `c` blocks sit at evenly
spaced factor offsets. The dropped edge of each `(block, factor)` cell is fixed;
the first occurrence uses the forward materialisation of §5.3, a later reuse the
reversed phase. Consequently every round is legal and meets new teams, and a short
prefix sees many distinct opponents quickly — e.g. for `N = 9, P = 4` the two
blocks use factors `{0, 2}` then `{1, 3}`, so all eight opponents are met after two
rounds. The cost is that I2/I5 on an incomplete layer may exceed their arithmetic
minimum; this is the deliberate trade in favour of the higher-priority opponent
spread.

### 6.3 Partial layer, even `N` — prefix-balanced factor plan

A partial even layer of `s < N−1` board slots assigns, to round `r`, a set of `s`
1-factors taken as the next `s` entries of the cyclic stream
`F_0, F_1, …, F_{N−2}, F_0, …`. Two properties are required and met:

- **prefix balance:** every round-prefix uses each 1-factor either `⌊·⌋` or `⌈·⌉`
  times — so opponent coverage grows as evenly as arithmetic permits;
- **slot regularity:** the factor occurrences are assigned to the `s` physical
  board slots by a proper edge-colouring of the (factor, round) bipartite
  incidence, so each slot carries a given factor at most once. A fixed slot
  therefore never repeats an opponent team (S4).

No floaters arise (S6a), as for full even layers.

### 6.4 Layer-shift balancing (odd `N`)

Rotating *all* team labels of a built layer by a fixed `σ ∈ ℤ_N`
(`t ↦ (t+σ) mod N`, board numbers unchanged) is a graph automorphism of the
layer. It preserves S2–S6, the colours later assigned, and per-round I1; it only
relabels *which* real teams carry that layer's descending floaters. After all
layers are built, one rotation per layer is chosen so that the combined descending
counts are as level as possible (minimising the descending spread, hence I2). This
prevents repeated small layers from charging the same teams — the rotation is the
only freedom used to optimise I2, and it cannot disturb any hard invariant.

---

## 7. Why the schedule satisfies the invariants

- **S1, S2.** Each layer assigns every team once to each of its board numbers
  (a 1-factor in the even case; a materialised 2-factor in the odd case, §5.3),
  and layers occupy disjoint board ranges. Summed over layers, every player plays
  exactly one game per round.
- **S3.** Every factor edge joins distinct teams, so no board pairs team-mates.
- **S4.** The factors partition the edges of `K_N`; within a layer a fixed board's
  factor index advances by one each round, so it never repeats an opponent team
  before the `N−1` round cap. Across layers the same holds per layer. Hence no
  player meets an opponent team twice.
- **S6a/S6b.** Even layers pair equal boards (1-factors); odd layers produce
  exactly one floater per block, on consecutive boards with the odd board
  descending (§5.3).
- **S6c.** In a full odd layer the dropped edges for a fixed block are
  vertex-disjoint across round-pairs, and the phase reversal swaps ascend/descend
  within a pair; in a partial odd layer each `(block, factor)` cell keeps one
  dropped edge whose phase flips on reuse. Either way no player repeats a floater
  role.
- **I1.** Established in §6.1 for full layers; §§6.2–6.3 give the best-effort
  prefix coverage for partial layers.

---

## 8. Colouring

Colour is assigned per round-pair, with no search.

**Round-pair colouring.** For a round-pair `(ρ, ρ′)` of *matches*, form the graph
`H` on the player set whose edges are the matches of `ρ` together with the matches
of `ρ′`. Every player has degree ≤ 2 in `H` (at most one board in each round), so
`H` is a disjoint union of paths and even cycles — in particular **bipartite**.
Fix a 2-colouring (a bipartition) `χ : P → {0, 1}` of `H`. Orient:

- in round `ρ`, the player with `χ = 1` takes White;
- in round `ρ′`, the player with `χ = 0` takes White.

Then every player that appears in both rounds gets White exactly once and Black
exactly once across the pair, and within each round the two endpoints of a match
receive opposite colours (a proper orientation). This yields **per-pair, per-player
colour balance**: over a completed round-pair each player has one White and one
Black.

Per-round **team** balance (S5) is a separate property: it requires that, in each
single round, exactly half of every team's players hold White. It is a structural
consequence of the schedule together with this colouring — note that the flip
between the two rounds of a pair makes a team's White count in the second round the
complement of its count in the first, so S5 holds in one round of a pair iff it
holds in the other — and it is enforced as a hard invariant (§3), checked directly
on the emitted rounds.

**Lone final round.** If `R` is odd the last round `ρ_R` has no partner. Colour it
by an **Eulerian orientation** of its team multigraph: each team plays an even
number `P` of boards, so the multigraph has all even degrees and decomposes into
closed walks; orienting each walk consistently gives every team equal White and
Black. The round is therefore self-balanced.

**The colour invariants follow.** Each player is balanced over every completed
round-pair, and over a lone final round it is balanced per team; this gives **C1**.
A colour can repeat only between the second round of one pair and the first round
of the next — i.e. only across an *even→odd* boundary — which is exactly **C3**,
and it makes a three-in-a-row impossible, which is **C2**.

---

## 9. Round count, prefixes, and rendering

**Round cap and prefixes.** Within every layer the factor assigned to each board
rotates by one per round-pair, so after `N−1` rounds all factors are exhausted;
hence `1 ≤ R ≤ N−1`. Moreover the schedule for `R` rounds is the
length-`R` prefix of the schedule for any larger round count up to `N−1`: a
short table is just the first `R` rounds of the full one, and remains valid. A
one-round event is round 1 of a valid table, already colour-balanced.

**Rendering.** Each round is emitted with boards ordered by board number — all
board-1 games first, then board-2, and so on — with a block's floater grouped with
its lower (odd) board. Within a board number, games are ordered by (White team,
Black team). A board `(w, b)` is printed as the pair of `(team letter, board
number)` for White then Black.

---

## 10. Determinism and the reference implementation

At three points the construction admits more than one admissible choice: the
materialisable one-odd 2-factorisation (§5.2), the internal repair that produces
it, and the layer rotations (§6.4). Each such choice is over a finite set, and the
**reference implementation fixes a canonical deterministic rule** for it (a fixed
search order with a fixed, seedless tie-break). Consequently:

> The map `(N, P, R) ↦ table` is a well-defined function. It is computed by
> [`molter_standalone.py`](molter_standalone.py), which depends only on
> `(N, P, R)` — there is no external seed or stored data.

This document specifies *what* a Molter table is (§§1–4) and *how* the method
constructs one (§§5–9). The exact canonical choices needed for byte-identical
output are defined operationally by the reference script, not restated here; a
re-implementation that wishes to reproduce the reference exactly should match that
script's output rather than re-deriving tie-breaks from prose.

---

## 11. Conformance

An implementation may target either level.

- **Validity conformance.** Its output, for every admissible `(N, P, R)`,
  satisfies S1–S6c and C1–C3 of §3 and respects the ideal priority I1-before-I2.
  This is the real contract: any constructor — this one, a SAT/CP/ILP solver, an
  official hand table — that passes §3 is acceptable, and validity is checkable
  independently of the construction.
- **Reproduction conformance.** Its output equals, board-for-board and
  colour-for-colour, the output of `molter_standalone.py` for the same
  `(N, P, R)`.

Validity is the definition; the construction of §§5–9 is one route to it, and the
reference script pins the single canonical table among the valid ones.
