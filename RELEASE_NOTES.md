# _Sharly Chess_ release notes

## General

- The language, federation and date format settings have moved from the browser to the main application window (5.1.0)
- Plugins are now installed and uninstalled from the main application window (5.1.0)
- The event export feature has been moved to the event's configuration window (5.1.0)
- A reminder to update player data is shown before distributing players across tournaments (5.1.0)
- The administration interface adapts to phone screens (5.1.0)
- A name format setting (Last First / Last, First / First Last / First, Last), with an option to display last names in capitals, sets how players' names are displayed, whatever the language (5.2.0)
- The update settings of the main application window have moved to a new About tab (5.2.0)

## Tournaments

- Exclusion of players (or teams) who have not played 50% of the games (or matches) in accordance with FIDE 6.6 in round robins (5.1.0)
- Separate players of the same club when distributing players on balanced tournaments, as much as possible (5.1.0)
- Team competitions can be sent to the _FFE_ website: teams and match reports are filled in from the tournament with the group account, for the competition, division and group chosen in the tournament properties (5.1.0)
- Team tournaments can be exported to the _Papi_ format, which describes them as individual Swiss tournaments (5.1.0)
- FIDE pairings (Dutch and team Swiss), team scores and tie-breaks, for individual and team tournaments, have been verified against _Gacrux_, an independent FIDE checker, on more than 100,000 generated tournaments (5.1.1)
- Tournaments can be imported from TRF06 and TRF16 files; the import dialog lists every adjustment made to fill in what these older formats lack (5.1.1)
- Scoring systems in which two draws are worth more than a win and a loss are refused, as are pairing-allocated byes worth more than a win or, with the standard scoring system, worth anything other than 1, ½ or 0 (5.1.1)
- Team names with characters the _FFE_ website does not store, such as the "œ" of "Sacré Cœur", no longer make the upload of team competitions fail (5.1.1)
- The French School Championship is sent to the school competitions of the _FFE_ website, with the national finals division pre-selected for the national final (5.1.1)
- Requested byes (half-point, full-point and zero-point) are now sent to _Sharly-Chess.com_, whose crosstables showed an empty cell and a wrong total for those rounds (5.1.2)
- The "All absent" button of the team check-in window is no longer labelled "Toutes présentes" in French (5.1.2)
- FIDE mode for Swiss tournaments: actions prohibited by the FIDE regulations are refused unless the tournament leaves FIDE mode, which is final once the first round is paired and recorded in the TRF (5.2.0)
- Team Swiss tournaments log the corrections to rounds already paired from and the changes to the number of rounds and the tie-breaks, each change asking only for a confirmation (5.2.0)
- Warnings follow the levels of the FIDE Technical Commission: a notice, a confirmation, or a double confirmation that spells out the consequences (5.2.0)
- In FIDE mode, once started, the points and the pairing-allocated bye value are fixed, the number of rounds and the tie-breaks change only after a double confirmation, and prohibited pairings are fixed after the first round (5.2.0)
- Allowing more than one half-point bye per player asks for confirmation in FIDE mode (5.2.0)
- After a TRF import, each imported round is checked against the pairing engine, and the rounds that differ are listed and logged (5.2.0)
- The TRF export is named after its use: _TRF26 (ITDX)_ for a partial file while the tournament is not finished or games have no result, where those games are unknown results; _TRF26 (final)_ for the final report, which alone carries the corrections made for the rating report (5.2.0)
- Games can be recorded as adjourned in Swiss and round-robin tournaments: they count as draws until their result is entered, which can be done at any time; the standings say they are provisional, and the TRF gives the games as unknown results. In FIDE mode, and in team Swiss tournaments, a result other than a draw entered after the next round is paired asks for confirmation and is logged (5.2.0)

## Players

- The player search can now be narrowed by federation, gender, age category and club (plus licence and league for _FFE_ searches), and the filters can be filled in one go from the criteria of any tournament of the event (5.1.0)
- Players removed by the deletion of unpaired players, or by an import replacing the existing players, are now also deleted on _Sharly-Chess.com_, instead of being brought back by the next synchronisation; re-imported players stay linked to their _Sharly-Chess.com_ registration (5.1.1)
- The _FFE_ player update now finds players whose licence number is wrong or unknown, by their _FIDE_ ID or else by their name and date (or year) of birth, and proposes the correct licence number; names are compared regardless of case and accents; players still not found despite their licence number (or FIDE ID for the FIDE database) are highlighted in the update window (5.1.1)
- Players without a _FIDE_ ID in the _FFE_ database, or with a _FIDE_ ID of 0 in an imported file, no longer prevent the synchronisation with _Sharly-Chess.com_ (5.1.1)
- Players' names are stored as entered; first names written all in capitals or all in lower case are displayed capitalised (5.2.0)
- The players tab is sorted by the name displayed first (5.2.0)
- Players can be marked as not eligible for byes (FIDE C.05:6.7.4): no Half-Point Bye can then be assigned to them (5.2.0)

## Pairings

- Ask if a round should be marked as completed for individual round robins (5.1.0)
- Added support for individual and team knockout pairings (single/double elimination, and two-game-match variants) (5.1.0)
- Results entered on an administration pairings screen now notify the other administration screens immediately, as results entered on an input screen already did (5.1.0)
- The team ranking of fixed-table tournaments (Molter) now shows the game points and the tie-breaks, which were all displayed as zero (5.1.0)
- Bonus / penalty points can no longer be given to an individual player of a team event from the player's record: team events adjust whole teams (5.1.0)
- Unpairing a board no longer renumbers the other tables of the round in compact table numbering (5.1.2)
- In FIDE mode, editing the pairings of a round by hand is validated against the pairing engine at the end, or cancelled; the next round waits for the validation (5.2.0)
- Manual pairings warn about repeated games, prohibited pairings, colour rules and ineligible pairing-allocated byes (5.2.0)
- In FIDE mode, each correction to the previous round is confirmed and logged; older rounds cannot be changed (5.2.0)
- A game of an older round found wrong can be corrected for the rating report only: the TRF and Papi exports give it as corrected, the TRF with a comment saying what the pairings and the standings used (5.2.0)
- A log of the pairing integrity breaches and settings changes, shown on the pairings page and written as comments in the TRF (5.2.0)
- Double round robins can choose whether the last two rounds of the first cycle are reversed, as recommended by FIDE to avoid three games in a row with the same colour (5.2.0)
- Buchholz tie-breaks can no longer be selected for team round robins, as for individual round robins (5.2.0)
- Full-point byes, deprecated by FIDE (C.05:6.7.4), are listed in the log, and so in the TRF comments and the FFE T2 minutes (5.2.0)

## Documents

- Place cards can now be edited with an embedded editor (5.1.0)
- A reminder to update player data is shown before generating place cards (5.1.0)
- Team tournaments paired on fixed tables (Molter) print the pairings document, with its options, in place of the match sheets (5.1.0)
- The FFE T2 minutes open with the events logged for the chosen tournaments (5.2.0)
- The rules of the accelerated systems can be printed, from the documents or from the pairing settings: the rules of the system, the groups, the virtual points granted round by round and the players of each group (5.2.0)

## Screens

- Long club names on ranking screens are cut short with an ellipsis instead of wrapping (5.1.1)

## Championships

- The championship rankings show the players' club, on screen and printed, and their year of birth on screen (5.1.1)

## Chess-Results

- The players' year of birth is now shown on _Chess-Results_ (5.1.1)
