# _Sharly Chess_ release notes

## General

- A name format setting (Last First / Last, First / First Last / First, Last), with an option to display last names in capitals, sets how players' names are displayed, whatever the language (5.2.0)
- The update settings of the main application window have moved to a new About tab (5.2.0)
- Only one _Sharly Chess_ runs on a data folder: starting it again opens the running one in the browser instead of starting a second server on another port, which would write to the same events (5.2.0)
- On Windows, the data is stored in the local application data (`%LOCALAPPDATA%\Sharly Chess\data`) instead of the Documents, which cloud services such as OneDrive can synchronise and so block the events while _Sharly Chess_ writes to them. The data of the former default folder is moved on the first start, the previous folder being deleted once the copy has been checked; a folder chosen in OneDrive, Google Drive, Dropbox or iCloud Drive is moved if the user agrees (5.2.0)
- Events are backed up as they change, and a backup can be restored over an event or beside it. The backups are kept beside the data folder rather than inside it, so that either folder can be moved without the other, and a folder of the user's own can be named for them (5.2.0)
- A refreshed admin view: a calmer and denser look set in Inter, cards and lists that show the status of each item as a coloured dot, the counts of the sidebar beside its entries, an edit button on each row of the players tab, the folding sections of the forms summarising their content, and fields that cannot be changed shown with a lock (5.2.0)
- The admin view can be light as well as dark: by default it follows the appearance of the system, and the settings of the application window can force it dark or light (5.2.0)
- Each browser tab is named after its page and event, such as "Players · Spring Open 2026", so that several open tabs can be told apart (5.2.0)
- The single screens are filtered by type with a row of chips instead of being folded away by type (5.2.0)
- The administration pages have been reworked with a more modern look (5.2.0)
- In the light admin view, the filtered players counter and the highlighted option of the drop-down lists are readable (5.2.1)
- Fix libraries missing in Linux Flatpak build (5.2.1)
- In the staff account form, every result of the player search fills in the account, including the results loaded after the first ones, which opened the player form, and the filter button that did nothing is gone. When replacing a player, the results loaded after the first ones also replace that player instead of creating a new one (5.2.2)
- In the settings of the application window, the fields all have the same width, and the labels of the checkboxes line up with the labels of the other fields (5.2.2)
- The plugins section follows the plugins enabled or disabled elsewhere, such as by importing an event that needs one, and the browser windows on the computer running _Sharly Chess_ follow the administration theme chosen in the application window, neither needing to be refreshed (5.2.2)
- The lists of events follow the plugins installed or uninstalled, so that an event that needs a plugin can be opened as soon as the plugin is installed, without refreshing the page (5.2.4)
- In every list that can be reordered by dragging, the place a dragged item will land is shown as an empty slot, instead of a second copy of the item (5.2.4)

## Tournaments

- FIDE mode for Swiss tournaments: actions prohibited by the FIDE regulations are refused unless the tournament leaves FIDE mode, which is final once the first round is paired and recorded in the TRF (5.2.0)
- Team Swiss tournaments log the corrections to rounds already paired from and the changes to the number of rounds and the tie-breaks, each change asking only for a confirmation (5.2.0)
- Warnings follow the levels of the FIDE Technical Commission: a notice, a confirmation, or a double confirmation that spells out the consequences (5.2.0)
- In FIDE mode, once started, the points and the pairing-allocated bye value are fixed, the number of rounds and the tie-breaks change only after a double confirmation, and prohibited pairings are fixed after the first round (5.2.0)
- Allowing more than one half-point bye per player asks for confirmation in FIDE mode (5.2.0)
- After a TRF import, each imported round is checked against the pairing engine, and the rounds that differ are listed and logged (5.2.0)
- The TRF export is named after its use: _TRF26 (ITDX)_ for a partial file while the tournament is not finished or games have no result, where those games are unknown results; _TRF26 (final)_ for the final report, which alone carries the corrections made for the rating report (5.2.0)
- A new _PGN (all rounds)_ export gives the games of every paired round in a single file, and both PGN exports now carry the results of the games, forfeits included, with the round dates, the players' _FIDE_ IDs and teams, and the time control (5.2.0)
- Games can be recorded as adjourned in Swiss and round-robin tournaments: they count as draws until their result is entered, which can be done at any time; the standings say they are provisional, and the TRF gives the games as unknown results. In FIDE mode, and in team Swiss tournaments, a result other than a draw entered after the next round is paired asks for confirmation and is logged (5.2.0)
- In individual Swiss tournaments, the players with the same rating and title can be ordered in the starting rank by drawing of lots instead of alphabetically (5.2.0)
- On wide screens, the tournaments tab shows three cards per row instead of two (5.2.4)

## Players

- Players' names are stored as entered; first names written all in capitals or all in lower case are displayed capitalised (5.2.0)
- The players tab is sorted by the name displayed first (5.2.0)
- Players can be marked as not eligible for byes (_FIDE_ C.05:6.7.4): no Half-Point Bye can then be assigned to them (5.2.0)
- The fees and payments of the registrations on _Sharly-Chess.com_ are imported into the players' owed and paid amounts when synchronising; payments recorded in _Sharly Chess_ are kept until they change on _Sharly-Chess.com_ (5.2.0)
- The payment column of the players tab can be shown even when no player has fees; it is hidden by default (5.2.0)
- The player search of the player form works again when a tournament is restricted to a club whose name contains an apostrophe (5.2.3)
- The Update button of the local _FIDE_ database rebuilds it, instead of doing nothing when _FIDE_ had not published a newer list since the copy was installed (5.2.4)

## Teams

- The teams tab has a search field that finds the teams by their name, affiliation, federation, captain or roster players; the search is kept while the tab is redrawn, after a team is dragged for instance (5.2.4)
- A team with no captain shows a warning, and all of a team's warnings are gathered behind a single warning sign, whose tooltip lists them one per line (5.2.4)
- A team being dragged is shown as a solid card or row, with no tooltips opening under the mouse, and the place it will land is shown as an empty slot (5.2.4)
- The team lists of the player form and the pairings ignore case and accents when sorting the teams by name (5.2.4)

## Pairings

- In FIDE mode, editing the pairings of a round by hand is validated against the pairing engine at the end, or cancelled; the next round waits for the validation (5.2.0)
- Manual pairings warn about repeated games, prohibited pairings, colour rules and ineligible pairing-allocated byes (5.2.0)
- In FIDE mode, each correction to the previous round is confirmed and logged; older rounds cannot be changed (5.2.0)
- A game of an older round found wrong can be corrected for the rating report only: the TRF and Papi exports give it as corrected, the TRF with a comment saying what the pairings and the standings used (5.2.0)
- A log of the pairing integrity breaches and settings changes, shown on the pairings page and written as comments in the TRF (5.2.0)
- Double round robins can choose whether the last two rounds of the first cycle are reversed, as recommended by FIDE to avoid three games in a row with the same colour (5.2.0)
- Round robins, individual and team, can be paired from a schedule set by hand (the new custom schedule variations) or edited after pairing from the Berger tables; the schedule is checked against the round-robin rules before it is saved (each pair meeting once, or twice, and no three games in a row with the same colour), and once results are entered, games played at the wrong boards can be corrected and a schedule breaking the rules saved anyway, the log and the TRF listing the rules it breaks for as long as it does (5.2.0)
- The previous and next tournament buttons are back beside the tournament selector of the pairings tab (5.2.0)
- Buchholz tie-breaks can no longer be selected for team round robins, as for individual round robins (5.2.0)
- The rating-based tie-breaks (ARO, TPR, APRO, PTP, APPO and RTNG) can give players without a FIDE or national rating a fixed rating, 1400 by default, instead of their estimated rating (5.2.0)
- In round robins with an odd number of players, the free round is not counted as a game: the Koya limit is half of the games each player can play, Rounds one Elected to Play leaves the free round out, and the Sonneborn-Berger cut applies to the games only (5.2.0)
- The Berger grid gives the tie-breaks of the standings, after the last finished round, when the later rounds are already paired (5.2.0)
- Full-point byes, deprecated by FIDE (C.05:6.7.4), are listed in the log, and so in the TRF comments and the _FFE_ T2 minutes (5.2.0)
- The arbiter now publishes each round: until then, the screens and the online services (_Sharly-Chess.com_, _Chess-Results_, _FFE_, custom uploads) stay on the previous round, while the new pairings can be checked and printed. A round can be published once the rounds before it are finished, and unpublished as long as it has no results (5.2.0)
- In round robins and fixed-table tournaments (Molter, Scheveningen), whose pairings are known in advance, the online services receive the pairings of every round as soon as they are made; publishing a round moves the screens on to it and makes its results public. Publishing replaces the End round button of round robins (5.2.0)
- When the tournament is shown on screens or sent to online services, the pairings page warns that a round is waiting to be published (5.2.0)
- In tournaments whose pairings are not known in advance, the Pair button offers to pair and publish a round in one go; the browser remembers the choice made for each event (5.2.4)
- In round robins, a player or team that withdrew is dropped from the standings, and their games annulled, as soon as they can no longer complete half of their games, instead of only once the last round has a result (5.2.0)

## Prizes

- Prize brackets can be duplicated, prize brackets can be copied to the other tournaments of the event, and categories to any prize bracket of the event, the copy of a main category being a regular category when its tournament already has one; criteria selecting individual players stay with their own tournament. Cloning a tournament now keeps the ranking basis of the prize categories and the complementary value of the prizes (5.2.0)
- Players without a club no longer win the prizes of club criteria: the club list of a criterion no longer offers an unnamed entry for them, and such an entry already selected is ignored (5.2.1)

## Documents

- The _FFE_ T2 minutes open with the events logged for the chosen tournaments (5.2.0)
- The rules of the accelerated systems can be printed, from the documents or from the pairing settings: the rules of the system, the groups, the virtual points granted round by round and the players of each group (5.2.0)
- Pairing place cards are not generated anymore for Pairing Allocated Byes (5.2.0)
- The text of the _FFE_ forms, the _FFE_ pairing sheet and the Chess960 positions can be selected and copied in the PDFs saved from Firefox (5.2.0)
- Documents have buttons at the top of the page to print them and to download them as PDF files; the documents with fields to fill in, such as the _FFE_ forms and the norm report, can also be downloaded as Word files. The files hold the values entered in the fields (5.2.0)
- A new rating achievement certificate states the highest intermediate FIDE rating a player reached during the tournament, game by game; it is signed by the chief arbiter of the tournament or by the arbiter chosen, and its text can be edited before printing (5.2.0)
- The norm report of a tournament in progress gives the figures of the 1.4.3d and 1.5.6a exceptions for the rounds being played, instead of zero while a round has no results (5.2.0)
- The statistics document downloaded as a PDF file shows the count at the end of each bar (5.2.4)
- The team selector of the documents lists the teams by name instead of in pairing order (5.2.4)
- On the standard team place card, the captain is printed under the team name instead of over the event name, and in the light admin view the previews of the place card templates are outlined so that the edges of the cards can be seen (5.2.5)
- A new arbiter norm report fills in the _FIDE_ Arbiter (FA1) or International Arbiter (IA1) norm form for the candidate chosen, with the figures of the tournaments chosen and, when one is chosen, the signee; every field can be edited before printing or downloading the form as a Word file (5.2.5)
- Opened from the pairings tab, the documents window proposes the round displayed, including after the next round has just been paired, instead of the round displayed when the tab was first opened (5.2.6)

## Screens

- The screens of the Screens tab, of the menus and of the display controllers are sorted by their displayed name (5.2.0)
- A timer can be put on several screens, multi-screens and rotators at once from the timers tab, which lists the screens displaying each timer; a screen showing another timer is moved to the chosen one (5.2.0)
- The screens shown to players and spectators have a cleaner look that keeps their density: each set opens with its name and what it shows on one line ("Round 3 · 5 games in progress"), the timer is a pill on that line, the alert message runs in a band along the bottom and scrolls only when it is too long to fit, and the menu between screens is a row of tabs (5.2.0)
- On the result entry screens, the games still to enter show an Enter button and the games entered step back, the last entry staying highlighted in green; on a phone, each game is a card. The result and check-in windows have large buttons, with the arbiter's forfeits set apart, and the buttons respond reliably on tablets (5.2.0)
- The timers and the alert message have fixed colours, a timer turning from green to orange then red and the message showing in a yellow band; the colours can no longer be chosen in the timer and screen settings (5.2.0)
- Image screens can show a timer, the image then starting below it (5.2.0)

## _Sharly-Chess.com_

- Several computers can synchronise the same event with Sharly-Chess.com: each sends only the changes it made, a player removed on the site after playing is kept until the arbiter withdraws or keeps them, a player moved to a tournament held on another computer is no longer deleted, conflicts no longer stop the synchronisation, changes the site refuses are reported, and a copied event asks to be connected again instead of disconnecting the original (5.2.0)
- The Sharly-Chess.com window says what each part covers: the registrations and the tournament settings, merged both ways when synchronising, and the pairings and results, published from the computer. Automatic publication is set per tournament for Sharly-Chess.com, the FFE and Chess-Results, the header switch turning it on or off for every tournament; new tournaments publish automatically to Sharly-Chess.com and the FFE (5.2.0)

## _FFE_

- _FFE_ arbiter titles follow the 2026 reform (Young, Match, Club and Open Arbiter); the FIDE arbiter title (FA or IA) is filled in from the _FFE_ database, and existing accounts are converted following the transition rules of the DNA, the former Elite arbiters becoming FIDE or International Arbiters (5.2.0)
- Improved player search in the _FFE_ database: online searches are faster, and players whose names the _FFE_ database cut or abbreviated (such as `MERCIER-PIQUEM.` for Mercier-Piquemal) are found from their full names, both by searches and when matching imported players (5.2.0)
- The FFE upload, the event clone and the event backup copy the event in one consistent snapshot, even while results are being entered (5.2.0)
- The online _FFE_ database is now used in priority over the local copy by default, with the local copy standing in when it cannot be reached; a switch in the databases window turns this off (5.2.2)
- Players without a rapid or blitz rating no longer receive their estimate by age as a national rating from the local _FFE_ database, whose file marks these estimates as national ratings (5.2.2)
- The banner of the players tab reads the rating lists from the same source as its Review window, so that it no longer announces changes the window does not show. It asks the online _FFE_ database at most every six hours for an event, unless a list changes or the arbiter acts on the check, and editing a player does not ask it again (5.2.2)
- Unrated players are ranked on the estimate the _FFE_ list gives them, as on the federal site, when it differs from the estimate of their category: an estimate their club asked for, or 1399 at a cadence where they lost a _FIDE_ rating, instead of the estimate by age, such as 799 for a U10 in rapid. The estimate of a younger category, which the list may still give a player who has since moved up, is still replaced by the estimate of their category. The rating check proposes these estimates to the players of existing events and no longer sets them apart as values typed by the arbiter (5.2.5)

## _French schools_

- The French schools database can be installed in the Linux Flatpak version (5.2.2)
- The French schools database is no longer offered for installation from a file, and the other databases can be installed from a file of any size (5.2.2)
