# _Sharly Chess_ release notes

## General

- Significantly improved speed of the application (5.0.0)
- Reorganize the desktop application into tabs (5.0.0)
- Card-based administration pages now offer a compact list view with key information in columns and expandable details (5.0.0)
- Added fédération CUR (5.0.0)

## Events

- Allow event creation as an organiser (5.0.0)
- A player with a fixed table number no longer results in empty table at the place they would have been assigned to (5.0.0)
- Added an FFE plugin option to specifically leave empty tables for fixed boards for compatibility with the FFE website (5.0.0)

## Players

- Players now have separate FIDE titles for the open and women titles, so a player can hold both at once (for example IM and WIM) (5.0.0)
- Titles are displayed intelligently: both are shown when they matter (e.g. FM and WIM), but the women title is hidden when the open title supersedes it (e.g. GM instead of GM/WGM) (5.0.0)
- When the FIDE database is installed locally, players looked up from it (including via an FFE search) have their women title filled in automatically (5.0.0)

## Teams

- _Sharly Chess_ now supports **Teams** events! (5.0.0)

## Prizes

- Added a quick way to generate prize categories for age categories and rating ranges (5.0.0)
- Duplication prize categories are now added immediately after the original (5.0.0)
- Duplicate prizes when duplicating a tournament (5.0.0)

## Fixed tables

The handling of fixed tables has been improved in several ways:

- The tables that the players would have been assigned to are no longer left empty (5.0.0)
- You can now assign any table number as a fixed table without having a duplicate table appearing (5.0.0)
- Changing fixed table assignment mid tournament is now correctly handled (previous round table assignments are kept) (5.0.0)
- In the admin pairings view you can choose to sort by pairing order or board number (5.0.0)
- In the associated document view you can choose if fixed tables are ordered by pairing order or board number (5.0.0)
- Pairing screens now have option to order by pairing order or board number (5.0.0)

### Special considerations when using the FFE (French federation) plugin

In order to maintain compatibility with the display of table numbers on the FFE website:

- By default we still leave the orignal table empty when the players are moved to a fixed table number
- In this compatibility mode, duplicate tables still occur when fixed table numbers are inside the normal table range
- This behaviour can be changed in the FFE plugin section of event's configuration

## Screens

- Menu support has been completely redesigned for a better experience (5.0.0)
- Families have been renamed **Multi-Screens** (5.0.0)
- Check-in screens now correctly use the configure column count (5.0.0)
- Vertical lines are now displayed between columns (5.0.0)
- A new **Chess 960** plugin allows you to display start positions for each round (5.0.0)

## Documents

- Norm reports generated before the end of the tournament now assume that players will play the remaining rounds for the purposes of displaying 1.5.6a and 1.4.3d (5.0.0)
- Title norm calculations now take women titles into account: opponents holding a WGM or WIM title are correctly counted towards the 1.4.5 and 1.4.3d requirements, even when they also hold an open title (5.0.0)
- The pairings document now has an option to include a federation column (5.0.0)
