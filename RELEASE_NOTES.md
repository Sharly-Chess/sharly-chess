# _Sharly Chess_ release notes

## General

- A name format setting (Last First / Last, First / First Last / First, Last), with an option to display last names in capitals, sets how players' names are displayed, whatever the language (5.2.0)
- The update settings of the main application window have moved to a new About tab (5.2.0)
- _FFE_ arbiter titles follow the 2026 reform (Young, Match, Club and Open Arbiter); the FIDE arbiter title (FA or IA) is filled in from the _FFE_ database, and existing accounts are converted following the transition rules of the DNA, the former Elite arbiters becoming FIDE or International Arbiters (5.2.0)

## Tournaments

- FIDE mode for Swiss tournaments: actions prohibited by the FIDE regulations are refused unless the tournament leaves FIDE mode, which is final once the first round is paired and recorded in the TRF (5.2.0)
- Team Swiss tournaments log the corrections to rounds already paired from and the changes to the number of rounds and the tie-breaks, each change asking only for a confirmation (5.2.0)
- Warnings follow the levels of the FIDE Technical Commission: a notice, a confirmation, or a double confirmation that spells out the consequences (5.2.0)
- In FIDE mode, once started, the points and the pairing-allocated bye value are fixed, the number of rounds and the tie-breaks change only after a double confirmation, and prohibited pairings are fixed after the first round (5.2.0)
- Allowing more than one half-point bye per player asks for confirmation in FIDE mode (5.2.0)
- After a TRF import, each imported round is checked against the pairing engine, and the rounds that differ are listed and logged (5.2.0)
- The TRF export is named after its use: _TRF26 (ITDX)_ for a partial file while the tournament is not finished or games have no result, where those games are unknown results; _TRF26 (final)_ for the final report, which alone carries the corrections made for the rating report (5.2.0)
- Games can be recorded as adjourned in Swiss and round-robin tournaments: they count as draws until their result is entered, which can be done at any time; the standings say they are provisional, and the TRF gives the games as unknown results. In FIDE mode, and in team Swiss tournaments, a result other than a draw entered after the next round is paired asks for confirmation and is logged (5.2.0)
- In individual Swiss tournaments, the players with the same rating and title can be ordered in the starting rank by drawing of lots instead of alphabetically (5.2.0)

## Players

- Players' names are stored as entered; first names written all in capitals or all in lower case are displayed capitalised (5.2.0)
- The players tab is sorted by the name displayed first (5.2.0)
- Players can be marked as not eligible for byes (FIDE C.05:6.7.4): no Half-Point Bye can then be assigned to them (5.2.0)

## Pairings

- In FIDE mode, editing the pairings of a round by hand is validated against the pairing engine at the end, or cancelled; the next round waits for the validation (5.2.0)
- Manual pairings warn about repeated games, prohibited pairings, colour rules and ineligible pairing-allocated byes (5.2.0)
- In FIDE mode, each correction to the previous round is confirmed and logged; older rounds cannot be changed (5.2.0)
- A game of an older round found wrong can be corrected for the rating report only: the TRF and Papi exports give it as corrected, the TRF with a comment saying what the pairings and the standings used (5.2.0)
- A log of the pairing integrity breaches and settings changes, shown on the pairings page and written as comments in the TRF (5.2.0)
- Double round robins can choose whether the last two rounds of the first cycle are reversed, as recommended by FIDE to avoid three games in a row with the same colour (5.2.0)
- Buchholz tie-breaks can no longer be selected for team round robins, as for individual round robins (5.2.0)
- Full-point byes, deprecated by FIDE (C.05:6.7.4), are listed in the log, and so in the TRF comments and the FFE T2 minutes (5.2.0)

## Documents

- The FFE T2 minutes open with the events logged for the chosen tournaments (5.2.0)
- The rules of the accelerated systems can be printed, from the documents or from the pairing settings: the rules of the system, the groups, the virtual points granted round by round and the players of each group (5.2.0)
- Pairing place cards can show the round number, and the tournament start date printed on place cards is no longer the end date (5.2.0)
