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

## Checking the _Sharly Chess_ pairings

Checking the pairings is needed for the _FIDE_ endorsement.

Pairings and checks entirely rely on the _BbpPairings_ pairing engine.

## Generate tournament pairings

Generate a random TRF file ``test.trf``:

``sharly-chess-<version>.exe --generate-tournament --output-file=test.trf``<br/>
or<br/>
``sharly-chess-<version>.exe -g -o test.trf``

Generate a random TRF file ``test.trf`` using a random seed (to easily reproduce the tests):

``sharly-chess-<version>.exe --generate-tournament --output-file=test.trf --random-seed=12345678``<br/>
or<br/>
``sharly-chess-<version>.exe -g -o test.trf -s 12345678``

## Check tournament pairings

Check the pairings of a TRF file ``test.trf`` (automatically writes file ``test.list``):

``sharly-chess-<version>.exe --check-tournament test.trf``<br/>
or<br/>
``sharly-chess-<version>.exe -c test.trf``

Check the pairings of a TRF file ``test.trf`` (write to file ``test2.list``):

``sharly-chess-<version>.exe --check-tournament --check-list-file=test2.list test.trf``<br/>
or<br/>
``sharly-chess-<version>.exe -c -l test2.list test.trf``

## Generate and check tournament pairings

Generate a random TRF file ``test.trf`` and check it:

``sharly-chess-<version>.exe --generate-tournament --output-file=test.trf --check-tournament``<br/>
or<br/>
``sharly-chess-<version>.exe -g -o test.trf -c``

## Generate and check 5000 tournament pairings at once

Use script ``/scripts/fide/generate_and_check_tournaments.py``.

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
