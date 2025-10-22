# _Sharly Chess_ - Checking the pairings

Checking the pairings is needed for the FIDE certification.

Pairings and checks entirely rely on the BbpPairings pairing engine.

## Generate tournament pairings

Generate a random TRF file ``test.trf``:

``sharly-chess-<version>.exe --generate-tournament --output-file=test.trf``<br/>
or<br/>
``sharly-chess-<version>.exe -g -o test.trf``

Generate a random TRF file ``test.trf`` using a random seed (to easily reproduce the tests):

``sharly-chess-<version>.exe --generate-tournament --output-file=test.trf --random-seed=12345678``<br/>
or<br/>
``sharly-chess-<version>.exe -g -o test.trf -s=12345678``

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
