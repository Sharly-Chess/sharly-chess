# Molter table — construction specification

This is a **self-contained, language-neutral specification** of how a Molter
pairing table is constructed. It depends on no source file and uses no
implementation-private names. A faithful re-implementation in any language that
follows this document **reproduces the same table byte-for-byte** for every
`(N, P, R)`.

Two levels of conformance are defined, and an implementer may target either:

- **Validity conformance** (the real contract). A table is a *valid* Molter
  table if it satisfies every hard invariant in §10 and respects the ideal
  priority (I1 before I2). Any construction — this one, a SAT/ILP solver, a
  hand table — that produces a table passing §10 is acceptable. Validity is the
  definition; this construction is one way to reach it.
- **Reproduction conformance** (this document). Follow §§1–9 exactly — the same
  arithmetic, orderings, constants, pseudo-random stream and tie-breaks — to
  emit the *identical* table this reference produces.

Throughout: `N` = number of teams, `P` = players per team (even, `≥ 2`),
`R` = number of regular rounds. All arithmetic on team indices is integer; `mod`
returns a non-negative result. Indexing is 0-based unless stated.

---

## 1. Objects and notation

- **Teams** are indices `0 … N−1`. The display letter of team `t` is `A` for 0,
  `B` for 1, …; for `t ≥ 26` it is the Unicode character `chr(ord('A') + t)`.
- **Boards / slots.** Each team fields `P` players on **boards** `1 … P`. Board 1
  is the strongest. Internally a board is a 0-based **slot** `s = board − 1`.
- **Player** = a pair `(t, s)`: team `t`, slot `s`. Its board number is `s + 1`.
- **Match** = an unordered pair of two players `{(t1,s1), (t2,s2)}` sharing a
  board pairing but with no colour yet.
- **Board (coloured)** = an *ordered* pair `(white, black)` of players.
- **Round** = a list of coloured boards. There are `N·P/2` boards per round.
- **Layer.** `N−1` boards on which, each round, the teams that play form a
  *complete graph* `K_N` (every team meets every other exactly once). `P` players
  give `P/2` two-board **blocks**; `m = (N−1)/2` blocks make one odd layer.
- **Round-pair.** Regular rounds are processed two at a time: round-pair
  `rp = ⌊r/2⌋`. Round `2·rp` is *free*, round `2·rp+1` is its *flip*.
- **Floater (odd N only).** When `N` is odd a board may pair two *different* board
  numbers `{k, k+1}` (k odd): the odd (stronger) player **descends**, the even
  player **ascends**. Each two-board block contributes exactly one floater per
  round.

A team's **descending-floater count** is how many times one of its players is the
descending side of a floater across all `R` regular rounds. **I2** is the
`max − min` spread of that count across teams.

---

## 2. Deterministic pseudo-random stream

The odd-`N` factorisation uses one seeded stream. It is a 64-bit LCG; reproduce
it exactly.

```
RNG(seed):
    state ← seed AND (2^64 − 1)

    next():
        state ← (6364136223846793005 · state + 1442695040888963407) mod 2^64
        return state

    randrange(stop):            # 0 ≤ result < stop
        return (next() >> 32) mod stop

    choice(list):
        return list[randrange(len(list))]

    shuffle(list):              # in-place Fisher–Yates, high index downward
        for i from len(list)−1 down to 1:
            j ← randrange(i + 1)
            swap list[i], list[j]
```

Every `shuffle`/`choice`/`randrange` below draws from the single stream created
with the stated seed, in the exact order the pseudocode visits them.

---

## 3. Top-level algorithm

```
generate(N, P, R):
    require P even, P ≥ 2
    require N ≥ 3
    if R is unset: R ← default_rounds(N)
    require 1 ≤ R ≤ N − 1

    if N is odd:
        matches ← build_odd_matches(N, P, R)              # §6
        rounds  ← colour_odd(matches, N)                  # §8
        emitted ← [ emit(rnd) for rnd in rounds ]         # §9
    else:
        matches ← build_even_matches(N, P, R)             # §5
        rounds  ← colour_even(matches, N, P)              # §5.3
        emitted ← [ emit_even(rnd, N) for rnd in rounds ] # §9

    return Table(N, P, rounds = emitted)

default_rounds(N):
    if N in {5, 7}: return N − 1
    return min(2, N − 1)
```

`build_*_matches` returns, for each of the `R` rounds, the list of uncoloured
matches. Colouring then orients each match into `(white, black)`.

---

## 4. Eulerian and flip colouring (shared)

A **free** round is coloured so each team gets exactly one White and one Black,
*and* so the next round's mandatory flip lands one White/one Black on every board.

```
eulerian_colour(matches):
    # Build the team multigraph: edge e joins team(matches[e].player0) and
    # team(matches[e].player1). Every team has even degree, so it splits into
    # closed walks. Orient each walk so its start team plays White on its
    # lowest-indexed incident edge, deterministically.
    edge_teams[e] ← (team of player0, team of player1) for each match e
    incident[t]   ← set of edges touching team t
    white_team[e] ← undefined for all e
    unused        ← all edge indices
    while unused not empty:
        start ← smallest team t with incident[t] non-empty
        cur ← start
        loop:
            e ← smallest edge index in incident[cur]
            (ta, tb) ← edge_teams[e]
            nxt ← (tb if ta = cur else ta)
            remove e from incident[cur] and incident[nxt]; remove e from unused
            white_team[e] ← cur
            cur ← nxt
            if cur = start: break
    # White is the player whose team is white_team[e]; the other is Black.
    return [ (p0,p1) if team(p0)=white_team[e] else (p1,p0)
             for e,(p0,p1) in matches ]

flip_colour(matches, prev):       # prev maps each player → had-White (bool)
    # Each player takes the opposite of its previous-round colour. The matching
    # pairs opposite previous colours, so White ↔ Black swap cleanly.
    return [ (p0,p1) if prev[p0] = False else (p1,p0) for (p0,p1) in matches ]
```

`prev` is read from the previous coloured round: White player → `True`, Black →
`False`.

---

## 5. Even `N` construction

### 5.1 One-factorisation of `K_N` (circle method)

`N` even ⇒ `K_N` splits into `N−1` perfect matchings. Team `N−1` is the pivot.

```
one_factorization(N):                 # returns N−1 matchings
    pivot ← N − 1
    ring  ← N − 1
    factors ← []
    for b from 0 to ring−1:
        matching ← [ edge(pivot, b) ]
        for i from 1 to N/2 − 1:
            matching.append( edge((b+i) mod ring, (b−i) mod ring) )
        factors.append( sort(matching) )
    return factors

edge(a, b) = (min(a,b), max(a,b))
```

### 5.2 Match construction

```
build_even_matches(N, P, R):
    factors ← one_factorization(N)
    ring ← N − 1
    for r from 0 to R−1:
        round ← []
        for b from 0 to P−1:                       # board slot b
            for (i, j) in factors[(b + r) mod ring]:
                round.append( match((i,b), (j,b)) )
        emit round
```

Every board in a slot pairs equal board numbers — **no floaters** (S6a). Slot `b`
plays matching `(b+r) mod (N−1)`, so a fixed slot meets a new team each round
(S4); when `N−1 | P` every team-pair appears equally each round (I1).

### 5.3 Even colouring

```
two_colour(N, matching_a, matching_b):     # proper 2-colouring of M_a ∪ M_b
    # M_a ∪ M_b is 2-regular with even cycles; colour each component, giving
    # colour 0 to the lowest team of the component. DFS, deterministic.
    build adjacency over edges of matching_a and matching_b
    colour[t] ← −1 for all t
    for start from 0 to N−1:
        if colour[start] ≠ −1: continue
        colour[start] ← 0
        DFS assigning colour[v] ← 1 − colour[u] across edges
    return colour

colour_even(matches, N, P):
    factors ← one_factorization(N); ring ← N − 1; last ← R − 1
    for r, match in enumerate(matches):
        if r is odd:
            output flip_colour(match, colours_of(previous output))
        else if r = last:                          # lone final free round
            output eulerian_colour(match)
        else:
            round ← []
            for b from 0 to P−1:
                a ← (b + r) mod ring
                col ← two_colour(N, factors[a], factors[(a+1) mod ring])
                for (i,j) in factors[a]:
                    if col[i] = 0: round.append( ((i,b),(j,b)) )   # i White
                    else:          round.append( ((j,b),(i,b)) )
            output round
```

`colours_of(round)` maps each White player → `True`, Black → `False`.

---

## 6. Odd `N` construction

```
build_odd_matches(N, P, R):
    m       ← (N−1)/2
    blocks  ← P/2
    factors ← odd_factorization(N)                 # §6.2 / §6.3
    use_affine_full ← (N in 7..99 and §6.2 succeeded)
    if factors is null: ERROR "no checked factorization"

    planning_counts ← [0]·N      # running descending-floater estimate per team
    layers ← []                  # list of (layer_matches, incidence)
    block_offset ← 0
    while block_offset < blocks:
        count ← min(m, blocks − block_offset)      # blocks in this layer
        layer_matches ← build_one_layer(N, R, block_offset, count,
                                        factors, use_affine_full,
                                        planning_counts)               # §6.6
        incidence ← descending_incidence(layer_matches, N)            # §6.7
        layers.append( (layer_matches, incidence) )
        (shift, shifted) ← best_layer_shift(planning_counts, incidence) # §6.7
        planning_counts ← planning_counts + shifted (elementwise)
        block_offset ← block_offset + count

    shifts ← optimise_layer_shifts([incidence for (_,incidence) in layers]) # §6.7
    out ← [ [] for _ in 0..R−1 ]
    for (layer_matches,_), shift in zip(layers, shifts):
        sm ← shift_layer_teams(layer_matches, N, shift)     # §6.7
        for r, rnd in enumerate(sm): out[r].extend(rnd)
    return out
```

### 6.1 Affine floater edge

```
affine_floater_edge(N, rp, block):
    half ← (N−1)/2
    s ← rp + block
    return edge(s mod N, (s + half + 1) mod N)
```

In one round-pair the `m` affine edges (one per block) are vertex-disjoint, so
exactly one team is *omitted* from floating and the rest float once.

### 6.2 One-odd 2-factorisation (`N` in `7..99`)

Goal: partition `K_N` into `m` 2-factors (every team has degree 2 in each), such
that each factor (a) **contains** the affine floater edges assigned to it, and
(b) is **materialisable** — its prescribed edges lie in a single odd-length
component and every other component is even. Returns `null` for `N < 7` or
`N > 99` (use §6.3 for `N = 3, 5`).

**Prescribed edges.** Factor `h = (rp + block) mod m` is used on cell
`(rp, block)`. Collect, per factor, the affine edges it must contain:

```
prescribed_edges(N):
    half ← (N−1)/2
    out[h] ← [] for h in 0..half−1
    for rp from 0 to half−1:
        for block from 0 to half−1:
            h ← (rp + block) mod half
            e ← affine_floater_edge(N, rp, block)
            if e not in out[h]: out[h].append(e)
    return out
```

**Length class.** Every non-loop edge `(a,b)` of `K_N` has a length class:

```
length_class(N, (a,b)):
    d ← (b − a) mod N
    return min(d, N − d) − 1            # 0 … (N−1)/2 − 1
```

**Driver.** Try up to 12 attempts; the first that yields a materialisable
factorisation wins.

```
odd_factorization(N):
    if N < 7 or N > 99: return null
    for attempt from 0 to 11:
        initial ← initial_factors(N, attempt)        # degree-valid
        if initial is null: continue
        repaired ← repair_factors(N, initial)        # materialisable
        if repaired ≠ null: return repaired
    return null
```

**`initial_factors(N, attempt)` — force prescribed edges, then fix degrees.**

```
initial_factors(N, attempt):
    half ← (N−1)/2
    rng  ← RNG(attempt + 1)
    edges ← all (a,b) with a<b
    prescribed ← { e → h } from prescribed_edges(N)

    if attempt even: perm ← [0,1,…,half−1]
    else:            perm ← [0,1,…,half−1]; rng.shuffle(perm)

    factor_of[e] ← perm[ length_class(N, e) ] for every edge   # initial guess
    factor_of[e] ← h for every prescribed (e → h)              # pin prescribed

    degrees[h][t] ← (count of factor_of edges incident to t in factor h)
    fixed ← keys(prescribed)
    free  ← edges not in fixed
    incident_free[t] ← free edges touching t

    score ← Σ over (h,t) of |degrees[h][t] − 2|
    plateau ← 0
    max_steps ← max(5000, N³)
    repeat max_steps times:
        if score = 0:
            return [ sorted(edges with factor_of = h) for h in 0..half−1 ]

        excess ← [ (degrees[h][t]−2, h, t) for all (h,t) with degrees[h][t] > 2 ]
        if excess empty: return null
        sort excess descending (by the triple)
        deficit_factors[t] ← [ h : degrees[h][t] < 2 ]

        moves ← []
        for (_, source, t) in first 30 of excess:
            cands ← copy of incident_free[t]; rng.shuffle(cands)
            for e in first 80 of cands:
                if factor_of[e] ≠ source: continue
                (a,b) ← e
                targets ← list( deficit_factors[a] ∪ deficit_factors[b] )
                if targets empty: targets ← [0,1,…,half−1]
                rng.shuffle(targets)
                for target in targets:
                    if target = source: continue
                    δ ← recolour_delta(degrees, e, source, target)
                    if δ ≤ 0: moves.append( (δ, e, source, target) )
                if len(moves) > 200: break
            if len(moves) > 200: break

        if moves empty:                              # forced random kick
            (_, source, t) ← rng.choice(excess)
            se ← [ e in incident_free[t] : factor_of[e] = source ]
            if se empty: return null
            e ← rng.choice(se)
            target ← rng.randrange(half); if target = source: target ← (target+1) mod half
            moves ← [ (recolour_delta(degrees, e, source, target), e, source, target) ]

        improving ← [ mv : mv.δ < 0 ]; neutral ← [ mv : mv.δ = 0 ]
        if improving non-empty:
            rng.shuffle(improving)
            pick the min-δ element of improving; plateau ← 0
        else if neutral non-empty and plateau < 2000:
            pick rng.choice(neutral); plateau ← plateau + 1
        else:
            sort moves ascending by δ
            pick rng.choice( first min(20,len(moves)) of moves ); plateau ← 0

        apply pick: factor_of[e] ← target; update the four degree counters;
                    score ← score + δ
    return null

recolour_delta(degrees, (a,b), source, target):
    old ← |deg[source][a]−2|+|deg[source][b]−2|+|deg[target][a]−2|+|deg[target][b]−2|
    new ← |deg[source][a]−3|+|deg[source][b]−3|+|deg[target][a]−1|+|deg[target][b]−1|
    return new − old
```

> The randomised tie-breaks above (`shuffle`, `choice`) draw from `rng` in the
> exact textual order shown. The min-δ pick when several share the minimum takes
> the *first* such element after the shuffle.

**Materialisability score of one factor** (lower is better; first component is
0 ⇔ materialisable):

```
factor_score(N, factor, prescribed_h):
    comps ← connected_components(N, factor)
    pteams ← teams covered by prescribed_h
    pcomps ← comps that intersect pteams
    odd    ← comps with odd size
    split_prescribed ← max(0, len(pcomps) − 1)
    prescribed_even  ← 1 if (exactly one pcomp and pteams ⊆ it and it has even size) else 0
    extra_odd        ← count of odd comps that do not contain all of pteams
    valid ← (split_prescribed = 0 and prescribed_even = 0 and extra_odd = 0)
    return ( 0 if valid else 1, split_prescribed, prescribed_even, extra_odd, len(comps) )
```

A factorisation's total score is the elementwise sum of its factor scores.
Component finding is a plain undirected traversal starting from `min(unseen)`.

**`repair_factors(N, initial)` — 4-edge switches to materialisability.**

```
repair_factors(N, initial):
    factors ← [ set(f) for f in initial ]
    edge_factor[e] ← its factor index
    prescribed ← prescribed_edges(N) as sets
    rng ← RNG(1)
    factor_scores[i] ← factor_score(N, factors[i], prescribed[i])
    current ← Σ factor_scores
    repeat N times:
        if current[0] = 0:
            return [ sorted(f) for f in factors ]
        order ← factor indices sorted by factor_score descending
        moved ← false
        for fi in order:
            if factor_scores[fi][0] = 0: continue
            best ← null
            for (other_factor, (e1,e2), (g1,g2)) in candidate_swaps(fi, limit=2000):
                # tentatively swap edges {e1,e2}⊂fi with {g1,g2}⊂other_factor
                apply swap; compute next factor scores for fi and other_factor;
                next ← current − fs[fi] − fs[other] + new_fi + new_other
                undo swap
                if next < current and (best is null or next < best.score):
                    best ← (next, other_factor, (e1,e2), (g1,g2), new_fi, new_other)
                    if next[0] < current[0]: break
            if best ≠ null:
                apply best swap; current ← best.score;
                factor_scores[fi], factor_scores[other] ← best.new_fi, best.new_other
                moved ← true; break
        if not moved: return null
    return null
```

`candidate_swaps(fi, limit)` enumerates 4-edge switches that keep the
factorisation a valid edge-partition (no degree change) while moving two edges
of `fi` out and two compensating edges in:

```
candidate_swaps(fi, limit):
    comps ← connected_components(N, factors[fi]); pteams ← teams of prescribed[fi]
    for each comp: bad ← (odd size and not pteams⊆comp) or (even size and comp∩pteams≠∅)
    bad_comps ← comps with bad = true; if none: return (nothing)
    targets ← bad_comps ++ all_comps; rng.shuffle(targets); yielded ← 0
    for first_comp in bad_comps:
        e_first ← edges of fi inside first_comp; rng.shuffle(e_first)
        for second_comp in targets:
            if second_comp is first_comp: continue
            e_second ← edges of fi inside second_comp; rng.shuffle(e_second)
            for e1=(a,b) in first 8 of e_first (skip if e1 ∈ prescribed[fi]):
                for e2=(c,d) in first 8 of e_second (skip if e2 ∈ prescribed[fi]):
                    for (g1,g2) in [ (edge(a,c), edge(b,d)), (edge(a,d), edge(b,c)) ]:
                        if g1=g2 or g1∈fi or g2∈fi: continue
                        of ← edge_factor[g1]
                        if of = fi or edge_factor[g2] ≠ of: continue
                        if g1 ∈ prescribed[of] or g2 ∈ prescribed[of]: continue
                        yield (of, (e1,e2), (g1,g2)); yielded += 1
                        if yielded ≥ limit: return
```

### 6.3 Small fixed factors (`N = 3, 5`)

These cannot use §6.2 (`N=3` is below range; `N=5` cannot meet perfect I2 while
keeping S6c). Use these fixed 2-factor sets verbatim:

```
N = 3:  factors = [ {(0,1),(0,2),(1,2)} ]
N = 5:  factors = [ {(0,3),(0,4),(1,2),(1,3),(2,4)},
                    {(0,1),(0,2),(1,4),(2,3),(3,4)} ]
```

For `N = 5` the planner is allowed to settle at I2 spread **2** (the proven
structural minimum under S6c).

### 6.4 Materialising one block (cell → matches)

A cell pairs a factor with a *dropped* edge; dropping it turns the factor's odd
component into a path laid across the block's two boards.

```
odd_edges_of(factor):                  # the factor's prescribed odd component, sorted
    comps ← connected_components(N, factor); pteams ← teams of prescribed[this factor]
    odd_comp ← the comp with odd size that contains all pteams
    return sorted edges of factor inside odd_comp

cycle_order(comp, factor):             # walk the component's cycle, lowest-first
    start ← min(comp); order ← [start]; prev ← −1; cur ← start
    loop:
        nxt ← smallest neighbour of cur in factor (within comp) other than prev
        if nxt = start: return order
        order.append(nxt); (prev, cur) ← (cur, nxt)

path_after_dropping(comp, factor, dropped=(start,end)):
    walk like cycle_order but with the dropped edge removed; begin at start,
    proceed to end, return the team sequence start … end

cell_matches(N, factor, dropped, odd_slot, even_slot, reverse):
    comps ← connected_components(N, factor)
    dcomp ← the comp containing dropped[0]
    path  ← path_after_dropping(dcomp, factor, dropped)
    if reverse: path ← reverse(path)
    out ← [ match((path[last], odd_slot), (path[0], even_slot)) ]   # the floater
    for i = 0,2,4,… < len(path)−1:  out.append match((path[i],odd_slot),(path[i+1],odd_slot))
    for i = 1,3,5,… < len(path)−1:  out.append match((path[i],even_slot),(path[i+1],even_slot))
    for comp in comps, comp ≠ dcomp:                 # even cycles, straight across
        cyc ← cycle_order(comp, factor)
        if reverse: cyc ← cyc[1:] ++ cyc[0:1]        # rotate by one
        for i = 0,2,… < len(cyc): out.append match((cyc[i],odd_slot),(cyc[(i+1) mod len],odd_slot))
        for i = 1,3,… < len(cyc): out.append match((cyc[i],even_slot),(cyc[(i+1) mod len],even_slot))
    return out
```

`odd_slot = 2·(block_offset + block)`, `even_slot = odd_slot + 1`. The floater's
descending player sits on `odd_slot` (lower board), the ascending on `even_slot`.

### 6.5 Full layer (count = m blocks)

```
full_layer(N, R, block_offset, count, factors):
    half ← (N−1)/2; out ← []
    for r from 0 to R−1:
        rp ← ⌊r/2⌋; reverse ← (r is odd); round ← []
        for block from 0 to count−1:
            h ← (rp + block) mod half
            dropped ← affine_floater_edge(N, rp, block)
            round.extend cell_matches(N, factors[h], dropped,
                                      2·(block_offset+block), 2·(block_offset+block)+1, reverse)
        out.append(round)
    return out
```

### 6.6 Choosing a layer (`build_one_layer`)

```
build_one_layer(N, R, block_offset, count, factors, use_affine_full, planning_counts):
    half ← (N−1)/2; nrp ← ⌈R/2⌉
    if count = half:                                   # a full layer
        if use_affine_full:
            plan_matches ← full_layer(N, R, block_offset, count, factors)
        else:                                          # N=3 or 5
            plan ← partial_plan(N, R, count, planning_counts, factors, max_spread=2)
            if plan is null: ERROR
            plan_matches ← materialise_plan(N, R, block_offset, plan, factors)
    else:                                              # a partial layer
        plan ← null
        if use_affine_full:
            plan ← affine_partial_plan(N, R, count, planning_counts, require_optimal=true)
            if plan is null:
                # try exact repair toward the lower bound, with offset candidates
                affine_offsets ← select_affine_offsets(N, R, count, planning_counts).offsets
                floor_offsets  ← floor_offsets(N, count)
                candidates ← [ floor_offsets ] ++ ([affine_offsets] if different else [])
                target ← 0 if (Σplanning + count·R) mod N = 0 else 1
                if R ≤ 12 or count·nrp ≤ 36:
                    for salt in 0..3:
                        for offsets in candidates:
                            plan ← partial_plan(N,R,count,planning_counts,factors,
                                                offsets, salt_start=salt, max_salts=1, max_spread=target)
                            if plan ≠ null: break
                        if plan ≠ null: break
                if plan is null:
                    plan ← affine_partial_plan(N, R, count, planning_counts, require_optimal=false)
        else:                                          # N=3 or 5 partial
            plan ← partial_plan(N, R, count, planning_counts, factors, max_spread=2)
        if plan is null: ERROR
        plan_matches ← materialise_plan(N, R, block_offset, plan, factors)
    return plan_matches

materialise_plan(N, R, block_offset, plan, factors):
    out ← []
    for r from 0 to R−1:
        rp ← ⌊r/2⌋; reverse ← (r is odd); round ← []
        for block, (factor_index, dropped) in enumerate(plan[rp]):
            round.extend cell_matches(N, factors[factor_index], dropped,
                                      2·(block_offset+block), 2·(block_offset+block)+1, reverse)
        out.append(round)
    return out
```

A **plan** has one row per round-pair; each row has one cell `(factor_index,
dropped_edge)` per block.

**Affine offsets** for `count < m` blocks:

```
floor_offsets(N, count):  half←(N−1)/2;  return [ (i·half) // count for i in 0..count−1 ]
```

**Affine partial plan** (uses the affine dropped edges directly):

```
score(counts) = ( max−min, max, Σ count², tuple(counts) )      # compared lexicographically

affine_contribution(N, R, offset):
    counts ← [0]·N; full ← ⌊R/2⌋
    for rp from 0 to full−1:
        (a,b) ← affine_floater_edge(N, rp, offset); counts[a]+=1; counts[b]+=1
    if R odd:
        (_,b) ← affine_floater_edge(N, full, offset); counts[b]+=1     # ascending only
    return counts

select_affine_offsets(N, R, count, initial):
    half←(N−1)/2; contrib[o] ← affine_contribution(N,R,o) for o in 0..half−1
    counts ← copy(initial); chosen ← []; remaining ← {0..half−1}
    repeat count times:                       # greedy: add the offset minimising score
        pick o in sorted(remaining) minimising score(counts + contrib[o]); add to chosen
        counts ← counts + contrib[o]; remove o from remaining
    repeat until no improvement:              # 1-for-1 swap improvement
        find (old in chosen, new in remaining) minimising score(counts − contrib[old] + contrib[new])
            that strictly improves score(counts); apply it
    return ( sorted(chosen), counts )

affine_partial_plan(N, R, count, initial, require_optimal):
    half←(N−1)/2; nrp←⌈R/2⌉
    (offsets, counts) ← select_affine_offsets(N, R, count, initial)
    total ← Σinitial + count·R; lb ← 0 if total mod N = 0 else 1
    if require_optimal and score(counts).spread ≠ lb: return null
    for rp from 0 to nrp−1:                   # build rows; verify disjointness
        for block, offset in enumerate(offsets):
            dropped ← affine_floater_edge(N, rp, offset); mask ← bit(dropped[0]) | bit(dropped[1])
            if dropped overlaps another cell in this round-pair, or in this block: return null
            cell ← ( (rp + offset) mod half, dropped )
    incidence ← counts − initial
    return (plan, incidence)
```

**Exact partial plan** (`partial_plan`) — a bounded backtracking search that
chooses, for each `(block, round-pair)` variable, a dropped edge from the cell's
factor's odd edges, minimising the descending-floater spread. It enumerates
target spreads from the best possible upward, and within a spread enumerates a
`low_bound` window; `salt` perturbs the tie-break hash.

```
partial_plan(N, R, count, initial, factors, offsets=floor_offsets(N,count),
             salt_start=0, max_salts=8, max_spread=null):
    half←(N−1)/2; nrp←⌈R/2⌉; full←⌊R/2⌋
    factor_edges ← [ odd_edges_of(f) for f in factors ]
    variables ← [ (block, rp) for block in 0..count−1 for rp in 0..nrp−1 ]
    units[v]  ← 2 if v.rp < full else 1      # a free-paired rp adds 2 incidences, a lone rp adds 1
    total ← Σinitial + count·R; avg_floor ← ⌊total/N⌋; max_init ← max(initial or 0)
    best_spread ← 0 if total mod N = 0 else 1
    node_budget ← 20000

    # Per variable, list the legal options. For a paired round-pair both teams of
    # the dropped edge gain a descending incidence; for a lone final round only
    # the descending endpoint does (two orientations, each adding 1).
    for v=(block,rp): factor ← (rp + offsets[block]) mod half
        options[v] ← for each edge (a,b) in factor_edges[factor]:
            if rp < full:   (factor, (a,b), a, b, 2, mask(a,b))
            else:           (factor, (a,b), b, −1, 1, mask(a,b))   # a ascends, b descends
                            (factor, (b,a), a, −1, 1, mask(a,b))   # b ascends, a descends

    tie_break(block, rp, dropped, salt):
        v ← (dropped[0]·1000003 + dropped[1]·9176 + block·131 + rp·8191
             + salt·2654435761) AND 0xFFFFFFFF
        v ← v XOR (v >> 16); v ← (v · 0x7FEB352D) AND 0xFFFFFFFF; v ← v XOR (v >> 15)
        return v

    last_spread ← (total if max_spread is null else max_spread)
    for spread from best_spread to last_spread:
        min_low ← max(0, ⌈(total − N·spread)/N⌉)
        for low_bound from avg_floor down to min_low:
            high ← low_bound + spread
            if high < max_init: continue
            for salt from salt_start to salt_start + max_salts − 1:
                if backtrack(...) succeeds within node_budget:
                    return (plan from chosen cells, counts − initial)
    return null
```

`backtrack` assigns variables one at a time:

1. **Bounds prune.** Let `need = Σ max(0, low_bound − counts[t])` and
   `cap = Σ max(0, high − counts[t])`. Fail if `need > remaining_units` or
   `cap < remaining_units`.
2. **Completion.** If all variables assigned, succeed iff
   `min(counts) ≥ low_bound and max(counts) ≤ high`.
3. **Reachability prune** (only once at least half the variables are placed and
   `low_bound > 0`): for each unplaced variable add, to every team it could still
   reach (an option whose mask avoids the round-pair's and block's used teams),
   one unit of *possible* incidence; fail if any team's `counts + possible <
   low_bound`.
4. **Variable order (MRV).** Among unassigned variables choose the one with the
   fewest *currently legal* options, where an option is legal iff its dropped
   edge does not reuse a team already used in this round-pair or this block, and
   placing it keeps both affected teams `< high` (a 2-unit option needs both
   endpoints `< high`; a 1-unit option needs only its descending endpoint
   `< high`). Break ties by first occurrence; stop early on a 0-option variable.
5. **Value order.** Sort that variable's legal options by
   `(primary, secondary, tie_break)` where, for a 1-unit option,
   `primary = counts[desc]` and `secondary = counts[desc]`; for a 2-unit option,
   `primary = counts[a]+counts[b]` and `secondary = max(counts[a], counts[b])`;
   and `tie_break = tie_break(block, rp, dropped, salt)`. Try them in order,
   recursing; undo on failure.

Disjointness within a round-pair and within a block is maintained by bitmask
sets (`row_used[rp]`, `block_used[block]`), guaranteeing S6b and S6c.

### 6.7 Layer-shift I2 optimisation

Rotating *all* team labels in a built layer by the same offset is an
automorphism — it preserves every pairing, floater legality, S6b/S6c, the
colours-to-be-assigned and per-round I1; it only relabels which real teams carry
that layer's descending floaters. After all layers are built, choose one rotation
per layer to minimise overall I2.

```
descending_incidence(layer_matches, N):
    counts ← [0]·N
    for round in layer_matches: for (p0,p1) in round:
        if p0.slot < p1.slot: counts[p0.team] += 1
        else if p1.slot < p0.slot: counts[p1.team] += 1
    return counts

shift_team_counts(counts, shift): result[(t+shift) mod N] ← counts[t]
shift_layer_teams(matches, N, shift): add shift (mod N) to every team index, keep slots

best_layer_shift(initial, incidence):     # greedy per-layer choice used during planning
    pick shift in 0..N−1 minimising score(initial + shift_team_counts(incidence, shift)) ++ (shift,)
    return (shift, shift_team_counts(incidence, shift))

optimise_layer_shifts(incidences):
    if empty: return ()
    if N^(#layers) ≤ 200000:               # exhaustive
        return the shift tuple minimising score(Σ shift_team_counts(incidence_i, shift_i))
    else:                                   # greedy seed + coordinate descent
        shifts ← per-layer best_layer_shift in order (accumulating counts)
        repeat until no single-layer change improves score:
            for each layer, try every shift; on the first layer with a strictly
            improving best shift, set it and restart the sweep
        return shifts
```

The exhaustive branch and the coordinate descent both compare by `score(...)`
(the lexicographic 4-tuple of §6.6).

---

## 7. Stacking and round cap

For `P` players there are `P/2` blocks. Odd layers take `m = (N−1)/2` blocks each;
even layers `N−1` boards each. `k = ⌊P/(N−1)⌋` full layers give per-round I1 (each
team-pair appears `k` times each round); a final partial layer covers the
remainder with best-effort spread. Because the factor/matching assigned to each
board rotates by round-pair, **any prefix `1 ≤ R ≤ N−1` is valid** — a short
table is just the first `R` rounds of the full one.

---

## 8. Odd colouring

```
colour_odd(matches, N):
    layer_size ← N·(N−1)/2          # boards in one full odd layer
    for r, match in enumerate(matches):
        if r is even:                # free round: Eulerian per layer-sized chunk
            round ← []
            for start = 0, layer_size, 2·layer_size, … < len(match):
                round.extend eulerian_colour(match[start : start+layer_size])
            output round
        else:                        # forced flip of the previous round
            output flip_colour(match, colours_of(previous output))
```

A round-pair (free + flip) balances every player; an odd `R` leaves a lone final
free round, coloured Eulerian (self-balancing since each team plays an even `P`).
No-tripling and the even→odd-only repeat rule then hold by construction.

---

## 9. Rendering (board order)

```
emit(round):                         # odd tables (may contain floaters)
    sort each board (white,black) by key:
        ( min(white.slot, black.slot), max(white.slot, black.slot),
          white.team, black.team )
    output each as TablePairing(letter(white.team), white.slot+1,
                                letter(black.team), black.slot+1)

emit_even(round, N):                 # even tables (no floaters)
    chunk ← N/2
    for start = 0, chunk, 2·chunk, … :
        sort round[start:start+chunk] by (white.team, black.team)
        output each as TablePairing(...)   # as above
```

`emit` groups all board-1 games first, then board-2, …, with each block's floater
grouped with its lower board. The result is the `rounds` of the table.

---

## 10. Conformance: the validity contract

A table is a **valid Molter table** iff it satisfies every hard invariant below
(checked on the regular rounds). The ideals are *priorities*, not requirements:
when two valid tables differ, prefer the one with better I1, then better I2.

**Hard invariants.**

- **S1** `P` is even; each round has exactly `N·P/2` boards.
- **S2** each player plays exactly one game per round and the same total over the
  event.
- **S3** team-mates are never paired.
- **S4** no player meets two opponents from the same team (forces `R < N`).
- **S5** each team plays as many Whites as Blacks.
- **S6a** even `N`: no floaters — every board pairs equal board numbers.
- **S6b** odd `N`: a floater joins only two *consecutive* boards `{k, k+1}` (k
  odd), the odd board descending; at most one descending floater per odd board
  per round.
- **S6c** over the regular rounds no player is the descending floater more than
  once, nor the ascending floater more than once.
- **C1** each player is colour-balanced over the regular rounds.
- **C2** no player plays the same colour three rounds running.
- **C3** a player's colour repeats only across an even→odd round boundary; every
  other boundary alternates.

**Ideals** (reached on complete tables; reported, never blocking):

- **I1** *(priority)* every round, each team meets every other equally — exact
  when `N−1 | P`.
- **I2** *(priority)* descending-floater counts differ across teams by as little
  as arithmetic allows (spread `≤ 1`, except `N = 5` where the structural minimum
  is 2).
- **I3** each team has as many ascending as descending floaters.
- **I4** each round spreads a team's players evenly across opponents.
- **I5** at most one descending and one ascending floater per team per
  round-pair — exact only for a single layer (`P = N−1`).

An independent implementation conforms at the **validity** level if its output
passes S1–S6c and C1–C3 and honours I1-before-I2; it conforms at the
**reproduction** level if, following §§1–9 exactly, it emits the identical
table.
