# _Sharly Chess_ - Tournaments lasting more than 30 days

FIDE rates a tournament as a single event only when it lasts 30 days or less. A
longer one is cut into slices of at most 30 days, and each slice is registered,
submitted and rated as a tournament of its own. _Sharly Chess_ calls those slices
**rating periods**.

Sources:

- FIDE Technical Commission Policies and Procedures Manual (version 2.0, 12 August
  2026), on the consistency checks a tournament handler makes against the rating
  server: the reference official list is "the list valid for the month in which the
  tournament started, for tournaments lasting more 30 days or less; the list valid for
  the current month, otherwise".
- FIDE Handbook `B.01` `1.1.4`: "In tournaments which last longer than 30 days, the
  opponents' ratings and titles used shall be those applying when the games were
  played." `1.4.6.1` names it as the exception to the norm rule that "the Rating List
  in effect at the start of the tournament shall be used".
- FIDE Handbook `C.07:10`: rating-based tie-breaks are not recommended when a player
  may hold more than one rating during the tournament; the first rating is the
  default.
- `VCL4THP` `Q210`–`Q216`, the acceptance questions this feature answers.
- [Comité de Bretagne, _Tournois FIDE en plusieurs tranches_](https://echecs-bretagne.fr/node/1928),
  the procedure French arbiters follow.

## Periods

A period covers a run of rounds: it starts at the round the arbiter marks and runs to
the round before the next period starts at. The periods of a tournament are therefore
contiguous and cover every round, and a period's dates are its rounds' dates.

Periods belong to the **tournament**, not the event: rounds and their dates are per
tournament, and two tournaments of one event may be cut differently, or one cut and
the other not.

Every tournament has at least one period, covering all its rounds. A tournament of 30
days or less has exactly that one, so the code has a single shape whatever the length
of the tournament, and nothing branches on the number of periods.

Everything the feature stores is added by migration `m105`:

| | |
|---|---|
| `tournament`.`multi_period` | The arbiter's flag: this tournament is reported in slices (`VCL` `Q210`) |
| `tournament`.`tie_break_rating` | Which slice the rating-based tie-breaks read (`C.07:10`) |
| `tournament_period`.`first_round` | The round a period starts at; round 1 always starts one |
| `tournament_period`.`plugin_data` | What a plugin keeps about one slice — the FFE its homologation number and the outcome of its uploads |
| `player_period` | A player's ratings and titles in one slice: `ratings`, `title`, `women_title` |

The flag is offered in the tournament form only once the tournament's dates span more
than 30 days, below the dates themselves. With it on, the schedule section shows one
card per period — its rounds, its dates and its length — and the rounds carry the
controls that move the boundaries. A period longer than 30 days is refused, and the
message names the first round played more than 30 days after the period started, which
is where it has to be cut.

## Ratings

A slice is rated on the ratings in force while it is played, so a player may hold a
different rating in each slice of a long tournament.

- `player`.`ratings` holds the player's **first** ratings — what `C.07:10` calls for
  by default, and the only ratings a short tournament ever has.
- `player_period` holds what the player was in a slice where that changed — the whole
  of the ratings, plus the titles `1.1.4` asks for — keyed by period.

Resolution (`Player.ratings_for(period)`): the ratings recorded for that period; else
those of the last earlier period of the same tournament that has any; else the
player's first ratings. A player whose rating never changed has no rows at all.

What a tournament is played on now — pairing, the players table, standings, the
exports — is its current slice's ratings: `TournamentPlayer.ratings` resolves through
`Tournament.current_period`, while `Player.ratings` stays the player's own.

Where a rating belongs to one game, it is that game's slice
(`TournamentPlayer.rating_and_type_in(period)`); where it summarises the tournament,
it is the current one. Anything printed for a round has to match the paper handed out
on the day, while "where do we stand" is a question about now:

| surface | rating shown |
|---|---|
| pairings screen, pairing and result modals | the round's slice |
| results entry | the round's slice |
| board and pairing print-outs | the round's slice |
| public board and results screens | the round's slice |
| crosstable and standings rating columns | current slice |
| players table | current slice |
| rating-based tie-breaks | the tournament's setting (`C.07:10`) |
| period report | that period |
| whole-tournament report | current slice |

`TournamentPlayer.rating_str_in_round(round)` answers for the screens, and
`NormOpponent.in_round(player, round)` for the norms — the opponent as the round that
was played knew them, which is what `1.1.4` asks for and what the norm rules then read
without knowing anything about slices.

Two averages a norm rests on read the slice too: `1.4.6`'s average of the opponents
counted (`Ra`), which holds one entry per game and so averages what each opponent held
on the day, and `1.5.6a`'s top-40 average, which is asked of each round separately.
The average rating printed in the tournament statistics is not a FIDE calculation and
summarises where the tournament stands, so it reads the current slice.

Norms need more than the ratings. `1.1.4` covers the opponents' **titles** too — a
title earned mid-event is the case it is written for — so a slice records those
beside the ratings. It says nothing of federations, which `1.4.3` and `1.4.4` count,
so those stay the player's current ones; and the applicant's own rating does not enter
a norm at all (`1.5.3` is about claiming the title afterwards).

Recording (`Player.update_ratings(ratings, period)`): a tournament's first period
records on the player, a later one against itself — so refreshing ratings for the
slice about to be played leaves the earlier slices, and the reports already made of
them, as they were. It is the step the FFE procedure puts before each tranche.

The player modal and the player-database update both record against the current
slice, and the comparison the update screen shows is made against it too. Everything
else a player update carries — name, title, federation, FIDE id — belongs to the
player whatever slice is being played. The modal lists the earlier slices' ratings
below the form, read-only: a correction lands on the slice being played, since the
earlier ones have been reported as they stand.

Ratings are keyed by period rather than by month on purpose. The FIDE database changes
day by day, and two slices starting in the same month are two submissions rated on
whatever was current for each; keying by month would force them to share one value,
and updating one tournament would silently change another's. Players are not shared
between tournaments today, so a period's ratings concern one tournament's field.

## Reporting

Each period is submitted as its own FIDE tournament, with its own registration, and
the file holds that period's rounds **only** — renumbered from 1, with the players who
played in them and points counted from those games alone.

Federations register one FIDE tournament per slice, in advance, and name it for the
rounds it covers. The 2026-27 season shows it plainly: "OP 6 Settimanale Social club
Rounds 1-2 / Rounds 3-4-5 / Round 6" (481714-6, Italy), "Zot en Boer 2026 Round 1"
through "Round 8" (486924-31, Belgium, September 2026 to May 2027), and "Pion Aalst
CK 2026-2027 Deel 1 Round 1-2 / Round 3 / Round 4-7" and onwards through four parts
(485824-75). Across the current French, Belgian, German and English listings, all but
one rated registration runs 30 days or less.

What such a file holds is visible in the reports:
[441469](https://ratings.fide.com/tournament_src_report.phtml?code=441469), "Belgian
Interclubs Round 2025-2026 **Ronde 11**", holds one round, numbered **1**, and each
player's points are that round's alone. An older pair shows both halves of the same
tournament:
[286873](https://ratings.fide.com/tournament_src_report.phtml?code=286873) is "OP
Settimanale Autunno 2022 Rounds 1-2-3-4" and
[286875](https://ratings.fide.com/tournament_src_report.phtml?code=286875) the same
tournament's "Rounds 5-6".

| | rounds 1-4 | rounds 5-6 |
|---|---|---|
| start date | 3 November 2022 | 1 December 2022 |
| rounds | 4, numbered 1–4 | 2, numbered **1–2** |
| players | 14 | 11 — those who played |
| points | from those four games | 2.0 and 1.5, from those two |
| Messina Enrico | 2141 | 2129 |
| Ficco Corrado | 1945 | 1965 |

Both players' ratings moved between the files, which is `1.1.4` in the wild, and each
file is sorted on its own ratings — so the starting ranks deliberately disagree
between submissions. The registration is named for the rounds it covers, a convention
worth copying.

The FIDE QC secretary described the opposite, the whole tournament with the rated
rounds' entries left blank. The practice above is what the rating server has accepted,
and the FFE's procedure agrees with it: one homologation number per slice, the complete
results published on the first slice's tournament for the players, and each later slice
submitted on its own with the earlier rounds removed.

A team tournament is reported the same way, and 441469 above is one: the file windows
what a team file names as well as its players — the teams that fielded a player in the
slice, numbered from 1, the players they fielded there as their rosters, the matches
of those rounds numbered from 1, and the match points those rounds were worth. A team
that sat the slice out is not in its file at all.

On the FFE side, the first slice's registration is also where the whole tournament is
published for the players. The FFE closes a registration once its slice has been sent
to FIDE, so the arbiter has to ask the federation to reopen the first one to go on
publishing the complete results there. The tournament form says so where the first
registration is entered.

In the app, a file per slice is offered below the whole-tournament entry in the export
menu, for the TRF and for the Papi alike, and a slice's file names itself after the
rounds it holds (`Championnat en tranches Rounds 4-5`) so that two files of one
tournament are told apart. An FFE upload sends the tournament entire under its own
registration and then the slice being played under that slice's, and a slice already
submitted is sent again on its own from the tournament's FFE menu — what a correction
to a rated tranche needs. Each slice answers for its own upload on the transfer
screen: whether it has been sent, when, and how it went.

Consequences to keep in mind:

- a period file cannot have its tie-breaks recomputed by a third party: the opponents'
  scores in it are period-local, and TRF carries no tie-break values;
- norms and rating cross-checks made from one file see that period's games only;
- a period file must never reach the pairing engine — it carries no colour or opponent
  history for the rounds it leaves out.

## Test data

Two scripts write an event whose tournament is under way and reported in slices, with
a rating history per player:

```
python -m scripts.test.generate_multi_period_event --path <data directory>
python -m scripts.test.generate_multi_period_team_event --path <data directory>
```

The rounds are laid out around the day they run, so the tournament is always being
played and the slices before the current one hold ratings of their own. `--rounds`,
`--boundaries`, `--interval` and `--seed` shape both; `--boundaries 4 6` cuts a
7-round tournament into R1–R3, R4–R5 and R6–R7.

The first writes an individual Swiss of `--players` players. The second writes an
interclubs season: `--teams` teams of `--boards` boards plus `--substitutes` roster
players, with the FFE plugin on and no round paired yet, so the pairing, the exports
and the uploads are all driven from the app. `scripts/test/multi_period_players.py`
holds what the two have in common — the players, their ratings per slice and the
schedule.

## Open points

- The round-referenced records a windowed file carries (`240`, `250`, `260`, `299`,
  `300`, `320`, `330`, `801`, `802`) are filtered to the rounds the file holds and
  renumbered with them, which follows from the file being a tournament of its own but
  is not written down anywhere. Worth confirming with the FIDE Technical Commission.
- Nothing records that a slice's file has been exported, so the app cannot say that
  results moved after one went out. The FFE uploads do track it, per slice.
