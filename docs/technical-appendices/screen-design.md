# _Sharly Chess_ - Designing the client screens

The client screens (`/view/screen/...`) are shown on projectors and televisions in the
playing hall, and on the PCs, tablets and phones that players and arbiters use to check
in and enter results. They are read from a distance, in a busy room, by people looking
for one line: their own name. This guide describes the visual language they share, so
that new screens, sets and modals look like the rest.

## Principles

- **Density first.** A projected screen must show as many rows as it can. Players should
  not have to wait for a page to rotate, and arbiters do not want them scrolling on an
  input screen. Prefer compact rows over generous whitespace.
- **Find your name by colour.** Pairings and input screens keep white on the left and
  black on the right, in the number of columns the screen is set up with. Players look
  for their name in their colour's column.
- **Keep the reading aids.** Dark column headers, the vertical bars between columns,
  striped rows and player titles all help the eye along a row; keep them.
- **One look, no settings.** Colours are part of the design, not options. The timer and
  the alert message have fixed colours, and no screen setting should let an organiser
  change them.
- **Calm by default.** Ink on white, with colour only where it carries meaning: green for
  done, the timer phases, the yellow alert message.

## Files

| What | Where |
|---|---|
| Styles | `src/web/static/css/user.css` |
| Set title | `src/web/templates/user/screen/sets/set_title.j2` |
| Timer | `src/web/templates/user/screen/timer.html`, `timer.js` |
| Alert message | `src/web/templates/user/screen.html` |
| Result and check-in modals | `src/web/templates/user/modals/` |
| Input rows and phone cards | `boards_set.html`, `team_matches_set.html`, `input_cards.html` in `src/web/templates/user/screen/sets/` |
| Fixed colours | `SharlyChessConfig.timer_colors`, `message_color`, `message_background_color` |

`user.css` is also loaded on the administration pages. Scope every rule to the client
screens (`#user-screen-content`, `.screen-top-nav`, `.input-screen` or an element that
only exists there), or it will change the administration too.

## Typography and colours

The screens use _Atkinson Hyperlegible Next_, a typeface designed for legibility at a
distance. Sizes follow the font size option of the screen: write them as
`calc(var(--font-size) / 100 * 1.3rem)` rather than fixed values.

| Token | Value | Use |
|---|---|---|
| `--screen-ink` | `#101418` | Text, title rule, the "Enter" button |
| `--screen-ink-secondary` | `#3a4250` | Details, ratings, titles |
| Column header | `#212529` | Table headers, white text |
| Green | `#0f6e3a` | Checked in, result entered, the last entry's edge |
| Pale green | `#d4edde` | The last entry made on the screen |
| Grey text | `#5b6370` | Games already entered on an input screen |
| Timer | `#0F6E3A`, `#B25E00`, `#B3261E` | The three timer phases |
| Alert message | `#FFC425` band, `#101418` text | The message along the bottom |

Avoid new accent colours. Blue in particular reads as a link or a button from another
application.

## Components

### Set title

Every set starts with `set_title(name, details)`: the name in bold, followed on the same
line by what is shown of it ("Round 5 · 3 games in progress"), over a 3px ink rule. The
titles are left-aligned so that they line up with the first column.

### Tables

Pairings, players, rankings and results are grids with a dark header, striped rows and a
2px dark bar between columns. Ratings and points are right-aligned next to the name they
belong to; the result sits midway between the two players.

### Timer

The timer is a pill at the right end of the first title line, next to a large clock. Its
text turns black or white depending on how light the phase colour is. A long text wraps
onto up to three lines, and the title line grows to match. On a narrow screen the timer
takes its own line above the titles.

### Alert message

The message is a rounded band fixed along the bottom of the screen, with a megaphone on a
slightly darker part of the band. A message that fits is centred and still; a longer one
scrolls at a steady 120 pixels per second, fading in and out at the edges.

### Input screens

Input screens keep the rows and columns of the pairings screen, a little taller so they
are easy to tap. A game still to enter shows a black **Enter** button in the result
column; an entered game is greyed out with a green tick beside its result, and the last
entry made on the screen is highlighted in pale green. Below 640px, where the two
players do not fit side by side, each game becomes a card with the players one above the
other. Cards are for phones only.

### Modals

Result and check-in modals share one structure: a header with the board number, a short
question, large choices (white wins, draw, black wins; check in or cancel), and the rarer
actions apart. Arbiter-only actions such as forfeits sit in their own section; clearing a
result is a red text button rather than a large one.

### Screen menu

The menu between screens is a row of rounded tabs; the current screen's tab is filled
with ink.

## Touch screens

Tablets, phones and some PCs are used by touch, where the browser keeps a tapped element
in its hover state and may treat the first tap as a hover only.

- Put hover styles inside `@media (hover: hover)`.
- Give tappable rows and buttons `touch-action: manipulation`.
- Disable a button only while its request runs, with `hx-disabled-elt`.
- Make tap targets at least as tall as a row of the input screen.

## Refreshes

The screens refresh every few seconds, and htmx replaces their content each time.

- Keep script state on `window` or `document.documentElement`, which survive the swap.
- Rebind on `htmx:afterSettle`, and use `hx-preserve` for elements that must not be
  replaced, such as the timer.
- Measure with a `ResizeObserver`: fonts load late, especially in Safari.
- An animation that must carry on across a refresh, such as the scrolling message, sets
  its position with `animation.currentTime`, since the element may be kept or replaced.

## Checking a change

Look at every change on a real screen, with the options organisers use: one to four
columns, small and large font sizes, a timer with a long text, a long alert message, a
menu, and the phone and tablet widths. Check it in Safari as well as Chrome.
