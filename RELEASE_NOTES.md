# _Sharly Chess_ release notes

## General

- _Sharly-Chess.com_ integration (4.0.0)
- Improved the navigation with keyboard shortcuts (4.0.0)
- Use Flatpak for Linux build (4.0.0)
- Rename _Upload_ menu to _Data Transfer_ (4.0.0)
- Fixed scrolling the first error into view on long forms (4.0.3)
- Fixed keyboard shortcuts (4.0.6)
- Search for GitHub updates every hour only (4.0.6)

## Events

- Automatically calculate event dates from tournament dates (4.0.0)
- Added an option to allow players in multiple tournaments (4.0.0)
- Fixed disabled fields behavior in event modal (4.0.1)
- Added duplication options to include pairings and define a start date (4.0.3)

## Tournaments

- Added round schedule to tournaments (4.0.0)
- Fixed schedule dates not selected by default (4.0.3)
- Fixed error when changing the date multiple times on creation (4.0.4)

## Players

- Added _rating_ and _rating_type_ CSV columns (4.0.0)
- Clarify gender naming (4.0.0)
- Fixed player update (4.0.1)
- Fixed player search keyboard selection (4.0.1)
- Invalidate year of birth < 1900 (4.0.2)
- Always export the year of birth in CSV export (4.0.2)
- Added _check_in_ column to CSV export (4.0.5)
- Download _FIDE_ database from _GitHub_ (4.0.5)

## Pairings

- Display absent players on top of unpaired players on the Pairings tab (4.0.0)
- Added a reminder to update the players' ratings before pairings on round #1 and for tournaments lasting on multiple FIDE periods (4.0.0)
- Clean display of pairing exceptions (4.0.2)
- Fixed Koya tie-break calculation (4.0.3)
- Fixed Round-Robin tournament round navigation (4.0.4)
- Also revert the result when permuting the colors (4.0.6)

## Prizes

- Fixed prize assignment on multiple main category override (4.0.2)
- Prevent duplicating prize criteria (4.0.3)
- Ensure consistent criteria order (4.0.3)

## Documents

- Added owed/paid totals to the check-in list (4.0.0)
- Added a sort option to the players list document (4.0.0)
- Set rank as the default sort option for Berger grids (4.0.3)

## _Sharly-Chess.com_

- Fixed tournament still uploadable after manual upload (4.0.2)
- Fixed unique constraint violation on tournament names (4.0.2)
- Added new player fields to the synchronisation (federation, _FFE_ league, _FFE_ licence, comment) (4.0.4)

## Plugins

### _Chess-Results.com_

- Moved the auto-upload options to the upload modal (4.0.0)
- Fixed round schedule upload (4.0.5)

## _FFE_

- Improved the upload modal (4.0.0)
- Relocate the rules upload to a group button on the FFE modal (4.0.0)
- Speedup _FFE_ database update (4.0.5)

### _ChessEvent_

- Synchronize button moved to the _Data Transfer_ menu (4.0.0)

### _FRA Schools_

- Download database from _GitHub_ (4.0.5)
- Fixed schools with no UAI code replacing each other (4.0.6)

## Handicap Games

- Added time control handicap info to tournament cards (4.0.0)
