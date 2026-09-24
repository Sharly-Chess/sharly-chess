# _Sharly Chess_ - _FIDE_ endorsement

## Useful links

### GitHub issue

- ["_FIDE_ endorsement"](https://github.com/Sharly-Chess/sharly-chess/issues/937)

### FIDE Handbook

- [Handbook C.04.A Appendix: Endorsement of a software program](https://handbook.fide.com/chapter/C04A)
  - Application for Swiss Pairing Program _FIDE_ Endorsement
  - Tournament Report File Format (version 2006)
  - Tournament Report File Format (version 2016)
  - List of _FIDE_ Endorsed Programs
  - Verification check-list
  - [Application for Swiss Pairing Program FIDE Endorsement (form)](https://www.fide.com/FIDE/handbook/C04Annex1_FE1.pdf)

### Pairing engines

- [_BbpPairings_](https://github.com/BieremaBoyzProgramming/bbpPairings)
- [_JaVaFo_](https://www.rrweb.org/javafo/aum/JaVaFo2_AUM.htm)

## Retrieving and running the checker and the generator

The check-list requires a Pairing and Tie-Break Checker (PTC) and a Random
Tournament Generator (RTG), both reachable from a command line and usable free
of charge by any stakeholder (C.04.A Annex 3, questions 19, 20 and 22). This
section is the one to give TEC: it is what belongs in the check-list's box for
*instructions on how to retrieve the PTC and the RTG*.

### Retrieving them

Both are part of _Sharly Chess_ itself; there is nothing else to download and
no licence to buy. The program is free software under the AGPL v3.0.

1. Download the release for your platform from
   [the releases page](https://github.com/Sharly-Chess/sharly-chess/releases).
2. Run it from a terminal with the options below. The options are handled
   before any window or server opens, so no interface starts and nothing is
   installed: the program does its work, prints its report and exits.

In the commands below, ``sharly-chess`` stands for however the release in
use is invoked, which differs by platform:

| Platform | What to run |
|---|---|
| Windows | ``sharly-chess.exe``, in the installation directory |
| macOS | the executable in ``/Applications/SharlyChess.app/Contents/MacOS/`` |
| Linux | ``flatpak run com.sharlychess.SharlyChess``, followed by the options |
| From source | ``PYTHONPATH=src python src/sharly_chess.py`` |

The macOS disk image holds ``SharlyChess.app``, which is dragged to the
Applications folder as usual; the command line is the executable inside its
bundle, which ``open`` does not reach because it passes no options on.

### The checker (PTC)

Read a TRF26 file and report what does not follow from the rules:

``sharly-chess --check-tournament test.trf``<br/>
or<br/>
``sharly-chess -c test.trf``

It reports both halves question 21 asks for:

- **the pairings**, round by round, each one re-paired from the position before
  it and compared with what the file records;
- **the standings**, against the criteria named in the file's own 212 record
  (or 202), in the order given there.

Three points about the standings, each of which would otherwise produce a
finding that is not an error:

- The comparison is on the *order*, not on the rank numbers. The rank field
  allows ties and programs number a shared rank differently, so the check asks
  only whether the file ever places a participant above one the criteria place
  higher.
- Participants the criteria leave level may be ordered any way at all — C.07
  Art. 4.2 has such ties drawn by lot — so only a pair the criteria actively
  reverse is reported.
- A file naming a criterion this program does not implement is reported as
  unchecked, rather than checked against the criteria that remain, which would
  pass for the wrong reason.

Add ``--check-list-file`` to write the report as JSON, which is what a run over
many tournaments wants:

``sharly-chess -c test.trf -l report.json``

### The generator (RTG)

Write a random tournament as TRF26:

``sharly-chess --generate-tournament --output-file=test.trf``<br/>
or<br/>
``sharly-chess -g -o test.trf``

Everything question 24 lists can be set, and anything left out is drawn rather
than given a fixed value (question 25):

| Option | |
|---|---|
| ``--players`` | number of players |
| ``--rounds`` | number of rounds |
| ``--ratings`` | the ratings to give the players, strongest first, comma-separated |
| ``--top-rating``, ``--rating-step`` | or build the ratings from a highest and a step |
| ``--full-point-byes`` | a fixed number (``4``) or a percentage (``5%``) |
| ``--half-point-byes`` | as above |
| ``--zero-point-byes`` | as above |
| ``--forfeit-wins`` | as above, counted in boards |
| ``--forfeit-losses`` | as above, counted in boards |
| ``--unusual-results`` | as above: a half point to one side only, or nothing to either |
| ``--acceleration`` | use the Baku acceleration method |
| ``--tie-breaks`` | the criteria the standings are ranked on, as TRF26 acronyms |
| ``--random-seed`` | repeat an earlier tournament exactly |
| ``--count`` | write a run of them, numbering the name where it carries ``%d`` |

For example, five hundred tournaments of 40 players over 9 rounds, with a
twentieth of the players taking a half-point bye in any round, three forfeits
per tournament, and the standings ranked on points, Buchholz cut 1 and
Sonneborn-Berger:

``sharly-chess -g -o "t%d.trf" --count 500 --players 40 --rounds 9
--half-point-byes 5% --forfeit-losses 3 --tie-breaks "PTS,BH/C1,SB"``

Each tournament is built the way the program builds a real one: the rounds are
paired by the pairing engine, the results are drawn from the ratings by the
statistical model of Otto Milvang's *Statistical model for chess tournament
simulations* (2024), and the standings come from the tie-break engine. The
file therefore states a tie-break list and standings that follow from it
(question 31), and nothing in it is invented after the fact.

Given ``--random-seed`` the generator repeats itself exactly; without one it
draws a seed, prints it, and does not repeat (question 30).

### Both at once

Generate a tournament and check it:

``sharly-chess -g -o test.trf -c``

## Generating and checking many at once

``scripts/fide/generate_and_check_tournaments.py`` writes a run of tournaments
and reads each one back through the checker, reporting the seed of any the two
disagree about:

``PYTHONPATH=src:. ./venv/bin/python scripts/fide/generate_and_check_tournaments.py 500``

Every parameter but the tie-break list is left to be drawn, so a run covers a
range of field and round counts. The criteria are given as a comma-separated
list, as they are to ``--tie-breaks``:

``... generate_and_check_tournaments.py 500 "PTS,BH/C1,SB"``

Given none, the run works through a range of lists instead, a tournament at a
time, so that the standings are checked against more than one set of criteria.

Our own checker accepting our own tournaments shows only that the two agree,
which is why question 33 asks for the other engine as well: at least 50,000
tournaments from each generator, verified by the other's checker. What this
script does catch is the two of them contradicting each other, where there is
no third party to blame.

## Checking against Gacrux

[Gacrux](https://github.com/OttoMilvang/TieBreakServer) is an open-source
pairing checker, tie-break checker and tournament generator by Otto Milvang
(MIT, copyright _FIDE_), presented at the 2026 _FIDE_ TEC Congress meeting.

It is not named in the check-list. What the check-list requires (Q33) is that
our pairing and tie-break engines be tested against *another publicly available
pairing and tie-break engine*, with at least 50,000 random tournaments generated
by the RTG of each engine and verified by the PTC of the other. Gacrux is such
an engine, and the only public one we know of that checks tie-breaks and not
only pairings — which is what makes it the natural counterparty, since our
tie-break engine is our own and no pairing-only checker can verify it.

We run it over the export of every test tournament.

These checks are left out of every default run, a bare ``pytest`` included:
they fetch Gacrux from GitHub, and they are a verification step for the
endorsement rather than a gate on every change. The ``gacrux`` marker has to
be asked for. Run them when the endorsement is being prepared, and after any
change to the tie-break engine:

``TEST_ENV=true ./venv/bin/pytest tests/gacrux -m gacrux``

What they verify is the tie-break engine, which is ours alone and which no
pairing checker can reach. Each tie-break exercise in `tests/json` is exported
as TRF26 and both engines are asked for the same tie-break, under the same
specifier, for every player; the values are compared one by one, over the 31
variants Gacrux implements — cuts, medians, the played and fore modifiers, the
Koya limits and the pre-March-2026 editions. The configured criteria of every
other tournament are checked the same way, against Gacrux's own verdict on
the standings, and the orderings that turn on Direct Encounter are checked on
the order they produce.

Pairings are not checked here: `scripts/gacrux/corpus.py` below does that over
123,000 tournaments rather than the few dozen this repository holds.

The same checks run on one event or file with:

``TEST_ENV=true PYTHONPATH=src:. ./venv/bin/python scripts/gacrux/check.py examples/events/minimal.sce``

Gacrux is fetched at the commit pinned in `tests/gacrux/harness.py` into
`tools/gacrux` on first use, and run as a subprocess: nothing of it is imported.
The report header names the commit, so a failure after a pin bump is read
against it. Disagreements are settled one by one in
`.context/tec/gacrux-reconciliation.md`, and the ones that turned out to be
Gacrux's are the known issues the harness recognises and works around.

## The published tournament corpus

Gacrux's author publishes ~123 000 generated tournaments at
[gacrux.no](https://www.gacrux.no) — 7 to 2 400 players, 5 to 91 rounds, with
byes, forfeits and accelerated rounds — each of them paired by Gacrux. Every
round is one our engine can be asked to reproduce from the position before it,
which is the round-by-round comparison the endorsement asks for:

``PYTHONPATH=src:. ./venv/bin/python scripts/gacrux/corpus.py ~/Downloads/tournaments --jobs 8 --report out/``

``--limit N`` per directory and ``--dirs 't_n9*'`` narrow the run;
``--max-players`` (default 700) leaves out the largest, which take minutes
each. Expect about 180 tournaments a minute on eight workers, so the whole
corpus is an overnight run. A tournament whose rounds we pair differently is
put to Gacrux's own checker: where it rejects the same rounds, the file is one
of the deliberately broken ones in ``misc`` and the two engines agree against
it, which the report says rather than leaving it as a difference.

Do not start a test run while it is going: pytest empties ``tests/tmp``, which
is where its workers keep their data.

Gacrux is MIT licensed (copyright FIDE). Its licence asks that a product which
embeds it link to [gacrux.no](https://www.gacrux.no) in its About section: the
test harness runs it, nothing ships it, so nothing is owed today, but the link
is due the day a build embeds a Gacrux component.
