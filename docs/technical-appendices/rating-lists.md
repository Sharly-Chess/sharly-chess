# Rating lists and tournament ratings

How a player's rating is chosen from the installed rating lists, recorded and
kept current (TEC Manual 3.9.5, VCL Q116–145). The code is in
`src/data/rating_sequences.py` (choice) and `src/data/rating_check.py`
(consistency check).

## A stored rating

`player`.`ratings` (and `player_period`.`ratings`) is keyed by cadence
(`1` standard, `2` rapid, `3` blitz):

```json
{"fide": 1850, "national": 1800, "manual": 1500, "k": 20,
 "pinned": "n:national:1",
 "origins": {"f": {"source": "fide", "version": "2026-10-02", "original": 1840},
             "n": {"source": "ffe", "version": "2026-10-01"}}}
```

- `fide` / `national`: the values the lists gave, by kind.
- `origins`: for each kind, the list it came from (`fide` or a national source
  id), the snapshot of that list (`version`, a date), and, once the arbiter has
  corrected the value, what the list gave (`original`). A value without an origin
  is taken to come from the FIDE list for `fide`, from the player's national
  list for `national`.
- `manual`: a value typed for a player no list rates. It has no kind and no
  source (suffix `E`). Absent, the plugins may prescribe one (hook
  `get_prescribed_rating`).
- `pinned`: on the tournament's cadence, the rating the arbiter chose among the
  player's ratings, as `<kind>:<family>:<cadence>`.

## Choosing the tournament rating

A tournament has a rating preference (`RatingPreference`: FIDE, national, one
then the other, highest, lowest — the TRF-26 Record 172 methods) and a sequence
of lists (`tournament`.`rating_sequence`, keys `fide:<cadence>` /
`national:<cadence>`, empty for the default of the cadence). A plugin may impose
the preference (`get_forced_rating_preference`) and supply the default sequence
(`get_default_rating_sequence`).

`resolve_rating`: the pinned rating while its list holds a value; else, for each
kind of the preference, the first list of the sequence holding a value of that
kind; else the manual value, else the prescribed one. A national list answers
for the FIDE kind through the FIDE rating it copies.

The **official rating** (`official_rating`) is the FIDE rating of the
tournament's cadence, or the FIDE standard one for a rapid or blitz player who
holds none, as the list gave it: an arbiter's correction changes the tournament
rating only.

## Consistency check

`check_ratings` reads, for the slice being played, the FIDE list by FIDE id and
each player's national list by national id, from the source
`DataSourceManager.list_source` gives (its installed copy, unless the user set
`read_online` on it; the installed copy alone for the automatic check), and
compares. A value read online records it (`origins.<kind>.online`). Changes of the tournament or official
rating are proposed; corrections and typed values are listed apart and kept
unless chosen; a change of source, snapshot or coefficient alone is applied
unasked. `automatic_check` runs it on the installed copies for the players tab
banner, again only once a list (`list_versions`) or a player changed.

## TRF

Field 001 (columns 49-52) always holds the official rating; the tournament
rating reaches the receiver through the starting ranks. What else is written
depends on the file (`TrfExport.build`, `TournamentPlayer._trf_national_players`):

| File | NRS records | Record 172 |
|---|---|---|
| For the pairing engine (`for_engine`) | none | none |
| Partial, during the tournament (ITDX) | the national record of the event's federation, and a pseudo-NRS record for the source of the tournament rating: `SSS`, `RRR` or `BBB` for a _FIDE_ list, `MMM` for a value no list supplied, the federation's code for another federation's list | the method of the preference, for the event's federation and for each other code present |
| Final report (`rating_report`) | the national record only where its rating ranked the player | the method of the preference, or `OTHER` when a value no list supplied ranked a player |

The pseudo-NRS convention is the TEC Manual's (3.9.6.2.b); the import reads
`SSS`, `RRR` and `BBB` back as _FIDE_ ratings of their cadence and `MMM` as the
value typed for the tournament's cadence. A slice of a tournament reported in
slices writes the ratings of its own period.
