# _Sharly Chess_ - Interface design

_Sharly Chess_ has two interfaces with different jobs:

- the **administration**, used by arbiters and organisers at a desk, for long sessions,
  to manage events, tournaments, players, pairings and screens;
- the **client screens** (`/view/screen/...`), shown on projectors and televisions in the
  playing hall, and on the PCs, tablets and phones that players and arbiters use to check
  in and enter results.

They share a few principles but not a look: the administration is dense, in a dark or
light theme, the screens are light and legible from a distance. This guide describes both as they are in
the code, so that new pages, screens and modals look like the rest. The code stays the
reference: when a pull request changes the look, it updates this guide too.

## Shared principles

- **Density over decoration.** Both interfaces show a lot of data. Prefer compact rows,
  tabular figures and quiet chrome to generous whitespace and ornaments.
- **One accent, used sparingly.** Colour carries meaning (the main action, a status, a
  timer phase, a warning); everything else is ink, surfaces and borders.
- **No colour settings.** Colours belong to the design, not to the organisers. Do not add
  options that let an event change them.
- **The same pattern everywhere.** A list, a modal or a status looks the same on every
  page. Reuse the macros and components below before writing new markup.
- **Text centred on its capitals.** Buttons, badges and pills trim their text to the
  capitals with `text-box-trim: trim-both` and `text-box-edge: cap alphabetic`, inside
  `@supports (text-box-trim: trim-both)`, and add padding to make up for the trimmed line.
  Otherwise the text sits visibly high (`base.css`, `user.css`).
- **Accessible by default.** Left-aligned text (never justified), visible focus rings,
  tooltips on icon-only buttons, and touch targets large enough for a finger.

## Files

| What | Where |
|---|---|
| Shared and administration styles | `src/web/static/css/base.css`, `admin.css` |
| Client screen styles | `src/web/static/css/user.css` |
| Page shell | `src/web/templates/common/base.html` |
| Administration layout | `src/web/templates/admin/common/base.html`, `common/admin_cards_container.html` |
| Components (buttons, menus, notes, badges, …) | `src/web/templates/admin/components/macros.j2`, `components/pairings.j2` |
| Modal shell | `src/web/templates/admin/components/modal.html` |
| Form and title macros | `src/web/templates/admin/common/macros.j2` |
| Collections | `src/web/admin/collection.py`, `src/web/admin/*/collection.py`, `*_components.j2`, `admin/common/collection.html` |
| Toasts | `src/web/messages.py`, `common/messages.html`, `common/alert.html` |
| Client screens | `src/web/templates/user/` |

All three stylesheets are loaded on every page. The body says which interface it shows
with `data-sc-interface` (`admin`, `client`, or `app` for the pages embedded in the
application window), and which theme with `data-bs-theme`. Scope administration rules to
`[data-sc-interface=admin]`, never to a theme, and client screen rules to the screens
(`#user-screen-content`, `.screen-top-nav`, `.input-screen`, or an element only they
have), or they will leak into the other interface. The rules of the components (the
`sc-*` classes) are the exception: only the components emit those classes, and the
plugins page also shows them in the application window, so they are not scoped.

## Administration

### Theme and typography

The administration follows the appearance of the system by default, or is forced
**dark** or **light** in the settings of the application window (`admin_theme` in the
configuration: `auto`, `dark` or `light`). Its controllers set `theme` from that setting
and `interface` to `admin`, and `macros.theme_script` puts both on `<body>` (htmx cannot
change the attributes of the body itself), resolving `auto` with `prefers-color-scheme`
and switching when the system does. That setting is the server's own: a client connected
over the network follows the appearance of its system, and can choose a theme for its
session in its profile (`SessionAdminTheme`).

Both themes share every rule; only the tokens differ, defined in
`[data-sc-interface=admin][data-bs-theme=dark]` and `…[data-bs-theme=light]` in
`base.css`. A rule never writes a colour of its own: it uses a token, and a new colour is
added to both blocks, so that it works in both themes.

The typeface is _Inter_ (`InterVariable`, with the `cv11` alternate), denser than the
screens' one, with tabular figures in tables. The root font size is 14px: every rem of the
administration scales from it, so density is set in one place.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bs-primary` | `#d7c9aa` | `#7d683a` | The accent, warm beige or bronze |
| `--bs-body-bg` | `#111215` | `#fbfbf9` | Page |
| `--pw-surface-bg` | `#1e2126` | `#ffffff` | Cards, the list surface |
| `--pw-surface-raised-bg` | `#2b2f36` | `#f3f1ec` | Hover, notes |
| `--pw-nav-bg` | `#1a1c20` | `#efede8` | Sidebar |
| `--bs-body-color` | `#ebe9e4` | `#1c1e22` | Text |
| `--bs-secondary-color`, `--bs-tertiary-color` | `#aaaeb6`, `#8b909a` | `#5c616a`, `#7c818a` | Secondary and tertiary text |
| `--bs-border-color` | `#2e3239` | `#e1ded6` | Borders and rules |
| `--pw-overlay-rgb` | `255, 255, 255` | `0, 0, 0` | Washes over a surface, as `rgba(var(--pw-overlay-rgb), .1)` |
| `--bs-border-radius` | `.5rem` | `.5rem` | Corners (`.375rem` small, `.75rem` large) |

The components have tokens of their own in the same blocks (`--pw-modal-bg`,
`--pw-table-header-bg`, `--pw-danger-text`, …). Use these variables rather than raw
colours. Public and private visibility have their own
variables, `--pw-visibility-public-color` and `--pw-visibility-private-color`.

### Layout

- **Sidebar.** The event's sections, with counts right-aligned in `.nav-count`. Below
  992px it becomes a drawer opened from the top bar.
- **Page header.** `admin_macros.admin_title(title, doc_ref)` gives the title with a link
  to the documentation before it. It also names the browser tab ("Players · Spring Open ·
  Sharly Chess"), through its `data-page-title` and the event's `data-page-context`, so a
  page without it leaves its tab unnamed. On the right, in this order: the **Details** switch and
  the list/card toggle (`collection_controls.html`), a settings button (an outline
  `components.button` or `modal_button` with `bi-gear-fill`), then the main action (kind
  `primary`, `bi-plus-lg`, "Create a …"). Each control has a tooltip. Below 768px the
  controls fold behind a "more" button, except those marked `.top-nav-keep`.
- **Content.** `section.admin-cards-section > .container-fluid`, with wider side padding
  from 992px.

### Collections

Lists of things (tournaments, players, screens, timers, …) are collections, declared in a
`collection.py` with an `AdminCollectionSpec`, and drawn from the macros of a
`*_components.j2` file. Each component macro takes `(item, view, placement)`, where
`view` is `card`, `list` or `details`.

- **List view.** A grid table (`ListLayout` and `ListColumn`), one row per item, with small
  header labels. The actions column comes last and is right-aligned.
- **Card view.** `CardLayout` with a header, a summary, a body, details and a footer. The
  cards sit in a grid of one to three columns whose rows line up.
- **Details.** A chevron opens a row's details; the **Details** switch opens them all. Lay
  details out with `.collection-details-grid` and `section.collection-detail-section > h6`.
- **Status.** A small dot before the name, in the status colour (`item_class` returns
  `collection-status-…`).
- **Actions.** Small outline buttons with a tooltip, built with the components:
  `bi-pencil` to edit, `bi-copy` to duplicate, `bi-trash` (danger) to delete. More
  actions go in a `menu_button` or a `split_button`.
- **Inline editing.** `collection_macros.column_edit_button`: a dotted underline and a
  faint pencil.
- **Empty states.** `components.empty_state(title)`, a dashed panel with the explanation
  given in its `{% call %}`. A missing value inside an item
  is shown in `text-danger` with `bi-exclamation-triangle-fill`, e.g. "No hours".

### Modals and forms

Every modal extends the modal shell, `admin/components/modal.html`, and fills its blocks:

```
{% extends '/admin/components/modal.html' %}
{% set modal_size = 'lg' %}            sm, md (default), lg, xl, wide, max or fit
{% block title %}…{% endblock %}       the h2 of the header
{% block subtitle %}…{% endblock %}    the object of the modal ("Tournament: …")
{% block toolbar %}…{% endblock %}     buttons acting on the contents, top right of the body
{% block body %}…{% endblock %}        form#modal-form, sections headed by section_heading
{% block footer %}…{% endblock %}      Cancel (the default), then the action
```

- The header holds the title, the subtitle and the close button, nothing else. The line
  naming the object of the modal always goes in `subtitle`, never at the top of the body.
- Buttons acting on what the modal shows (Add, Generate, …) go in `toolbar`, never in the
  header.
- The footer is `components.cancel_button()` then the main action, a `components.button`
  of kind `primary` with `form="modal-form"` ("Save" or "Create"). `footer_start` holds an
  action set apart on the left, such as Print.
- `modal_doc` sets an icon after the title, opening the modal's page of the documentation.

Deletions use `common/modal/delete_modal.html`, itself on the shell: the object goes in
its subtitle, and its button is set with the `delete_label` and `delete_icon` blocks.
Section headings (`components.section_heading`) stay quiet so that the accent goes to the
main button.

Build fields with the macros of `admin/common/macros.j2` (`text_input`, `number_input`,
`select_input`, `switch_input`, `checkbox_input`, `date_input`, …), which all go through
`_generic_input`:

- labels are written `_('%(string)s:', string=_('Name'))`, placeholders
  `_('E.g.: %(string)s', …)`;
- errors come from `errors[name]` and show under the field;
- `tooltip_text` adds an ⓘ after the label, `help_text` a line under the field;
- `default_checkbox` adds a "Use default" box that fills in and locks the default value;
- a disabled field keeps the look of the others, with a muted value and a lock.

### Buttons and icons

Build buttons with `components.button` rather than markup:

- the kind says its role: `primary` is the one main action of a page or modal (a tonal
  wash of the accent, not a solid block), `secondary` steps back behind it (Cancel),
  `outline` is a toolbar action, `danger` and `outline-danger` destroy something, `link`
  and `plain` have no frame;
- `size='sm'` inside lists and cards;
- `icon` takes a Bootstrap Icons class (`bi-…`) or a name of the icon list of
  `macros.j2` (`save`, `cancel`, `delete`, `confirm`, `warning`, …), set at the same gap
  from the label everywhere;
- `icon_only=true` shows the icon alone: the label becomes its tooltip and its accessible
  name;
- `allowed=false` with a `reason` disables the button and shows why in a tooltip;
- `href` makes it a link that looks like a button, for a page to open rather than an
  action.

`modal_button(url, label, …)` opens a modal (`modal_trigger_attrs(url)` gives the same
attributes to a card or a row). Menus are a `menu_button` (icon-only too) or a
`split_button` holding `menu_item`s, `submenu`s, `menu_header`s and `menu_divider`s; a
menu of checkboxes in a form starts with `menu_select_all`. Choices joined in one group
(All / In play, the view mode, a radio row) are a `segmented` control of `segment_radio`,
`segment_checkbox` or `segment_button`.

An icon before a text that is not a button is `components.icon_text(icon)`, which keeps
the same gap and centres the icon on the text; an icon alone is `components.icon`.

### Feedback

- **Toasts.** `Message.info/success/warning/error(request, …)`. They stack at the bottom
  right (full width on a phone). Information and success fade after ten seconds; warnings
  and errors stay until closed.
- **Notes.** `components.note(level, body)` (`info`, `warning`, `danger`, `secondary`), a
  quiet raised panel with the icon in the note's colour; `actions` sets buttons on its
  right, `compact` makes it smaller. `components.banner` gives a dismissible message band.
- **Badges.** `components.badge(kind, text)` (`primary`, `neutral`, `info`, `warning`,
  `danger`, `success`) carries its own ground, readable in both themes; tags are
  `tag_badge` and `tag_badges`. The pairings have their own in `components/pairings.j2`:
  points, the side that advances in a knock-out, and the tie awaiting a choice.
- **Legends.** `components.legend` and `legend_item(icon)` explain the icons of a list.
- **Confirmations.** `warning_macros.j2` gives a one-step confirmation for risky actions
  and a two-step one, defaulting to Cancel, for the riskiest.
- **Status bars.** A table can carry a `.table-status-bar` along its top, with a dot, an
  action button and a close button.

### Phones

Below 992px the sidebar becomes a drawer; below 768px the toolbar folds, modals fit the
width, detail grids go to one column and the pairings become one card per board. Size
things with `var(--vw)` and `var(--vh)` rather than `vw`, `vh` or percentages of the
window.

## Client screens

The screens are read from a distance, in a busy room, by people looking for one line:
their own name.

- **Density first.** A projected screen must show as many rows as it can. Players should
  not wait for a page to rotate, and arbiters do not want them scrolling on an input
  screen.
- **Find your name by colour.** Pairings and input screens keep white on the left and
  black on the right, in the number of columns the screen is set up with.
- **Keep the reading aids.** Dark column headers, the bars between columns, striped rows
  and player titles all help the eye along a row.
- **Calm by default.** Ink on white, with colour only where it means something: green for
  done, the timer phases, the yellow alert message.

### Typography and colours

The screens use the **light** theme and _Atkinson Hyperlegible Next_, a typeface made for
legibility at a distance. Sizes follow the screen's font size option: write them as
`calc(var(--font-size) / 100 * 1.3rem)` rather than fixed values.

| Token | Value | Use |
|---|---|---|
| `--screen-ink` | `#101418` | Text, the title rule, the "Enter" button, the selected tab |
| `--screen-ink-secondary` | `#3a4250` | Details, ratings, titles |
| Column header | `#212529` | Table headers, with white text |
| Green | `#0f6e3a` | Checked in, result entered |
| Pale green | `#d4edde` | The last entry made on the screen |
| Grey text | `#5b6370` | Games already entered |
| Timer | `#0F6E3A`, `#B25E00`, `#B3261E` | The three timer phases (`SharlyChessConfig.timer_colors`) |
| Alert message | `#FFC425` band, `#101418` text | The message along the bottom |

### Components

- **Set title** (`user/screen/sets/set_title.j2`). Every set starts with
  `set_title(name, details)`: the name in bold, then what is shown of it on the same line
  ("Round 5 · 3 games in progress"), over a thick ink rule, left-aligned.
- **Tables.** A dark header, striped rows and a dark bar between columns. Ratings and
  points sit next to the name they belong to; the result sits midway between the players.
- **Timer** (`user/screen/timer.html`, `timer.js`). A pill at the right end of the first
  title line, next to a large clock, its text black or white depending on the phase
  colour. A long text wraps onto up to three lines; on a narrow screen the timer takes its
  own line above the titles.
- **Alert message** (`user/screen.html`). A rounded band along the bottom, with a megaphone
  on a darker part of the band. A message that fits is centred and still; a longer one
  scrolls at a steady 120 pixels per second, fading at the edges.
- **Input screens.** The rows and columns of the pairings screen, a little taller to tap.
  A game still to enter has a black **Enter** pill in the result column, without making its
  row any taller; an entered game is greyed; the last entry is highlighted in pale green.
  Below 640px each game becomes a card with the players one above the other. Cards are for
  phones only.
- **Modals** (`user/modals/`). Result and check-in modals share one structure: the board
  number, a short question, large choices (white wins, draw, black wins; check in or
  cancel), and the rarer actions apart, such as forfeits in an arbiter section.
- **Menu.** A row of rounded tabs; the current screen's tab is filled with ink.

### Refreshes

The screens refresh every few seconds, and htmx replaces their content each time.

- Keep script state on `window` or `document.documentElement`, which survive the swap.
- Rebind on `htmx:afterSettle`, and use `hx-preserve` for elements that must stay, such as
  the timer.
- Measure with a `ResizeObserver`: fonts load late, especially in Safari.
- An animation that carries on across a refresh, such as the scrolling message, sets its
  position with `animation.currentTime`, since its element may be kept or replaced.

## Touch screens

Tablets, phones and some PCs are used by touch, where the browser keeps a tapped element
in its hover state and may take the first tap as a hover only.

- Put hover styles inside `@media (hover: hover)`.
- Give tappable rows and buttons `touch-action: manipulation`.
- Disable a button only while its request runs, with `hx-disabled-elt`, never for good.

## Components and their guard

The components are shown, in both themes, in a gallery at `/dev/components`, available
when the application runs in development; its end-to-end test checks their contrast. Add
a component there when you add it to `components/macros.j2`, with a unit test in
`tests/unit/test_admin_components.py`.

`scripts/lint/template_components.py`, run by pre-commit and by a unit test, counts the
markup the components replace (buttons, modal triggers, menu items, icon spacing, fixed
colour utilities, …) in the administration and plugin templates, against
`template_components_baseline.json`. It fails when a count goes up, and when one goes down
without the baseline being lowered (`--update-baseline`); `--report` gives the totals. What
remains is written by hand on purpose: keyboard-driven search lists, the round navigation,
buttons inside input groups.

## Checking a change

Look at every change in the running application before asking for a review:

- in Chrome and Safari, at desktop, tablet and phone widths;
- for the administration, with long names, empty collections and both list and card views;
- for the screens, with the options organisers use: one to four columns, small and large
  font sizes, a timer with a long text, a long alert message and a menu;
- in English and French, whose texts are often longer.
