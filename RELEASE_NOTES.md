# _Sharly Chess_ release notes

## General

- The language, federation and date format settings have moved from the browser to the main application window (5.1.0)
- Plugins are now installed and uninstalled from the main application window (5.1.0)
- The event export feature has been moved to the event's configuration window (5.1.0)
- A reminder to update player data is shown before distributing players across tournaments (5.1.0)
- The administration interface adapts to phone screens (5.1.0)
- On Linux, the server starts again without a display (on a headless server), in console mode (5.1.3)

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
- Direct encounter tie-breaks with games missing between the tied players now follow _FIDE_ Art. 6.3, and AOB is shown to three decimals (5.1.3)
- The French School Championship now covers high schools: a category (primary schools, middle schools, high schools) is chosen in the tournament properties, high schools playing on 4 boards with a roster of up to 5 pupils including at least 1 girl and 1 boy; departmental team finals can be chosen as a phase (5.1.3)
- Importing a TRF file of a tournament in progress no longer marks every player as withdrawn: the rounds not paired yet stay unpaired, with the byes already requested for them (5.1.4)

## Players

- The player search can now be narrowed by federation, gender, age category and club (plus licence and league for _FFE_ searches), and the filters can be filled in one go from the criteria of any tournament of the event (5.1.0)
- Players removed by the deletion of unpaired players, or by an import replacing the existing players, are now also deleted on _Sharly-Chess.com_, instead of being brought back by the next synchronisation; re-imported players stay linked to their _Sharly-Chess.com_ registration (5.1.1)
- The _FFE_ player update now finds players whose licence number is wrong or unknown, by their _FIDE_ ID or else by their name and date (or year) of birth, and proposes the correct licence number; names are compared regardless of case and accents; players still not found despite their licence number (or FIDE ID for the FIDE database) are highlighted in the update window (5.1.1)
- Players without a _FIDE_ ID in the _FFE_ database, or with a _FIDE_ ID of 0 in an imported file, no longer prevent the synchronisation with _Sharly-Chess.com_ (5.1.1)

## Pairings

- Ask if a round should be marked as completed for individual round robins (5.1.0)
- Added support for individual and team knockout pairings (single/double elimination, and two-game-match variants) (5.1.0)
- Results entered on an administration pairings screen now notify the other administration screens immediately, as results entered on an input screen already did (5.1.0)
- The team ranking of fixed-table tournaments (Molter) now shows the game points and the tie-breaks, which were all displayed as zero (5.1.0)
- Bonus / penalty points can no longer be given to an individual player of a team event from the player's record: team events adjust whole teams (5.1.0)
- Unpairing a board no longer renumbers the other tables of the round in compact table numbering (5.1.2)
- Updating the ratings from the reminder shown before pairing the first round no longer skips the window asking what to do with absent players, who were then paired (5.1.3)

## Documents

- Place cards can now be edited with an embedded editor (5.1.0)
- A reminder to update player data is shown before generating place cards (5.1.0)
- Team tournaments paired on fixed tables (Molter) print the pairings document, with its options, in place of the match sheets (5.1.0)

## Screens

- Long club names on ranking screens are cut short with an ellipsis instead of wrapping (5.1.1)

## Championships

- The championship rankings show the players' club, on screen and printed, and their year of birth on screen (5.1.1)

## Chess-Results

- The players' year of birth is now shown on _Chess-Results_ (5.1.1)
