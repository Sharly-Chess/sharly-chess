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
