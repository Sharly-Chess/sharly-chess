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
range of field and round counts.

Our own checker accepting our own tournaments shows only that the two agree,
which is why question 33 asks for the other engine as well: at least 50,000
tournaments from each generator, verified by the other's checker. What this
script does catch is the two of them contradicting each other, where there is
no third party to blame.
