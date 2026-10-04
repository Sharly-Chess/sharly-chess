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
 "pinned": "national:n:1",
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
  player's ratings, keyed as a rating of a sequence.

## Choosing the tournament rating

A tournament has a sequence of ratings (`tournament`.`rating_sequence`, empty
for the event's default), each naming its list, its kind and its cadence:

| Key | Rating |
|---|---|
| `fide:<cadence>` | the _FIDE_ list's rating |
| `national:f:<cadence>` | the _FIDE_ rating the player's national list gives |
| `national:n:<cadence>` | the national rating of the player's national list |

The prebuilt sequences offered (`sequence_options`) name only the ratings the
event's national list publishes: `national_cadences` and `fide_cadences` of its
data source.

The rating preference (`RatingPreference`, the TRF-26 Record 172 methods) is
what the sequence amounts to (`sequence_preference`): the kinds it tries, in the
order it first tries them. It is stored with the sequence (`tournament`.`rating_preference`), which on its own does not tell highest and lowest apart.
The event's preference shapes the default sequence of its tournaments. A plugin
may impose the preference (`get_forced_rating_preference`), which locks the
event's, and the sequence of each cadence (`get_forced_rating_sequence`), which
is then the only one offered and replaces any stored sequence.

`resolve_rating`: the pinned rating while its list holds a value; else the first
rating of the sequence the player holds, or for highest and lowest the higher or
lower of the first _FIDE_ and the first national ones; else the manual value,
else the prescribed one: the rating a plugin prescribes (`get_prescribed_rating`),
else the tournament's `unrated_rating`, else the event's, 1400 by default. A
plugin that prescribes one describes its rule (`get_prescribed_rating_rule`), and
the forms then show the field locked.

The **official rating** (`official_rating`) is the FIDE rating of the
tournament's cadence, or the FIDE standard one for a rapid or blitz player who
holds none, as the list gave it: an arbiter's correction changes the tournament
rating only.

## Consistency check

`check_ratings` reads, for the period being played, the FIDE list by FIDE id and
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
value typed for the tournament's cadence. A period of a tournament reported in
periods writes its own ratings.
