# _Sharly Chess_ release notes

## General

- Each event keeps a journal of what is done to it, shown in a new Journal page: results entered, changed or cleared, pairings, byes, penalties, players, teams, tournaments and staff accounts, with when it was done, by whom (the administrator or a staff account, even one deleted since) and from where (the computer running _Sharly Chess_, another device, a screen or _Sharly-Chess.com_), the names being kept as they were at the time. The arbiters can add notes to it, filter it by tournament, kind of action, person or origin, and download it; it follows the changes as they happen, and travels with the event when it is exported unless left out (5.3.0)

## Tournaments

- A player who leaves an individual round-robin can be replaced, from the player form, by a newcomer who takes over their seat from a chosen round: their Berger number, their remaining opponents and their colours. The tournament keeps its rounds and its schedule, both players are ranked on the games they played, and in the tie-breaks the seat counts as a single opponent worth the points of all who held it. The Berger grid gives the seat one line, and the TRF gives the tournament as a custom round-robin with a comment for each replacement (5.3.0)
- The "Export event (SCE)" button of the warning shown before a tournament export that loses data opens the event export options, with the players included by default: the file it produced held no players, teams or pairings (5.3.0)

## Players

- The players tab follows the check-ins and results entered elsewhere, on another computer, a screen or the pairings tab, without being reloaded: the rows that change are updated in place and light up briefly, and a player who no longer matches the filters leaves the table, so that the list of the players not yet checked in shrinks as they arrive. A player checked in from the tab keeps their row while its countdown runs (5.3.0)
- The rows of the players tab are lighter, so that long lists load faster (5.3.0)
- The rating check proposes to remove a national rating that no list gave, such as an _FFE_ estimate imported as a national rating, when the national list finds the player and gives them no national rating at that cadence (5.3.0)

## Pairings

- The pairings tab follows the results and check-ins entered elsewhere without being reloaded: the boards whose result changes are updated in place and light up briefly, the players and teams checked in move between the lists, and the button to the next round appears once the round is finished. Nothing changes while the arbiter is typing, choosing, dragging or has a window open: the update waits until they have finished (5.3.0)
- The tournaments of an event can be paired and published at once from the All tournaments button of the pairings tab, whose badge tells how many are ready: the next round of the Swiss, Keizer and knock-out tournaments is paired, deciding what becomes of their absent players as the Pair button does, and the next round of the round robins and fixed-table tournaments is published once the rounds before it are finished. The first round, a round opening a new period and a round that needs a confirmation are still paired from the page of their tournament, and a tournament left out, such as a one-off blitz, is left out again the next time (5.3.0)

## Staff

- Choosing a person among the search results of the account form no longer fails with an error when a role has already been given for several tournaments (5.3.0)

## Screens

- The screens follow the changes as they happen rather than every ten seconds: a result updates only the games and players it concerns on the pairings, result entry, players and check-in screens, the rankings are drawn again at once, and a change to a screen, such as its font size, shows straight away, as does what is sent to a channel, even one going through several screens (5.3.0)
- A screen is drawn again only when something it shows has changed: a player withdrawn from another tournament no longer redraws every screen of the event (5.3.0)
- Timers are simpler to set up and to keep up to date: each hour is either the start of a round, worded automatically ("Round 3 starts in 4 minutes"), or a moment with a label of its own, with a preview of what the screens will show; a tournament's schedule can be copied into a timer, and copied again after it changes; a quick countdown shows "Next round in 10 minutes" in one step; an hour can be postponed together with the later hours of its day; the delays read as the colours the timer goes through, and may be 0; and the screens showing a timer are chosen in the timer's own form (5.3.0)
- On a players screen shown through a display controller, tapping a player opens the result window of their game, instead of sometimes opening the window of another board of the round; a game is always found by its own identifier, so that no screen can open another board's result window (5.3.0)
- The background of image screens can use a colour extracted from the image in one click or be filled by a blurred version of the image (5.3.0)

## Documents

- Appreciation certificates can be printed for the players of a prize category, from the place cards document, now named Place cards and certificates: every player of the category gets a certificate, whatever the number of its prizes, or only the prize winners, those of all the categories of a prize group at once if needed. Besides the player's information, the templates of the certificates offer the player's rank in the category, the number of players in the category, the performance for the categories ranked by performance, and the prize won in the category. A standard certificate template is provided (5.3.0)
- The round-robin grid is listed among the documents before the tournament is paired, so arbiters can see it is there, and both it and the round-robin schedule explain, when asked for too early, that they cannot be printed until the tournament is paired, rather than the grid being missing from the list and the schedule printing a draw the pairing can still change (5.3.0)

## __Sharly-Chess.com__

- The pairings published on _Sharly-Chess.com_ show the table numbers shown in _Sharly Chess_: when a fixed board leaves the board it displaces empty, as in _FFE_ events, a player with a fixed board is shown at that board instead of at the board the game would have had without it (5.3.0)

## _FFE_

- On the _FFE_ pairing sheets (Fiche d'appariement), the letter printed for each team is its fixed-table letter, the one its place in the pairing order gives it and the one the tables and the pairings use, rather than the rank of its name in the alphabet, so that once the team order is changed the letters follow it (5.3.0)

## _ChessEvent_

- The rapid and blitz estimates of the _FFE_ imported from Chess-Event arrive as estimates rather than as national ratings: the _FFE_ database _ChessEvent_ reads types them N (5.3.0)
