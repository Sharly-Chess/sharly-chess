/* Keyboard use of the players table: ↑/↓ move from row to row, Enter opens
   the focused player, Space checks them in or out. */

function playersTableRows() {
    return Array.from(document.querySelectorAll('#players-table tbody tr[id^="player-"]'));
}

// Where the focus is in its row, to put it back at the same place in
// another row, or in the same row once it has been replaced.
function playersTableFocusSlot(row, element) {
    if (element === row) {
        return null;
    }
    const cell = element.closest('td');
    if (!cell) {
        return null;
    }
    const focusables = Array.from(cell.querySelectorAll('button, a[href], [tabindex="0"]'));
    return {cell: cell.cellIndex, index: focusables.indexOf(element)};
}

function focusPlayersTableRow(row, slot, focusVisible = true) {
    let target = row;
    if (slot) {
        const cell = row.cells[slot.cell];
        const focusables = cell
            ? Array.from(cell.querySelectorAll('button, a[href], [tabindex="0"]'))
            : [];
        target = focusables[slot.index] || row;
    }
    target.focus({preventScroll: true, focusVisible: focusVisible});
    target.scrollIntoView({block: 'nearest'});
}

window.addEventListener('keydown', function (event) {
    const row = event.target.closest && event.target.closest('#players-table tbody tr[id^="player-"]');
    if (!row || event.ctrlKey || event.altKey || event.metaKey) {
        return;
    }
    if (event.target.closest('.dropdown-menu') || event.target.getAttribute('aria-expanded') === 'true') {
        return;
    }

    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        if (event.shiftKey) {
            return;
        }
        const rows = playersTableRows();
        const next = rows[rows.indexOf(row) + (event.key === 'ArrowDown' ? 1 : -1)];
        event.preventDefault();
        if (next) {
            focusPlayersTableRow(next, playersTableFocusSlot(row, event.target));
        }
        return;
    }

    const checkIn = event.target.matches('[data-sc-row-check-in]');
    if (event.target !== row && !checkIn) {
        return;
    }
    if (event.key === 'Enter' && event.target === row) {
        const open = row.querySelector('[data-sc-row-open]');
        if (open) {
            event.preventDefault();
            htmx.process(open);
            open.click();
        }
    } else if (event.key === ' ' || (event.key === 'Enter' && checkIn)) {
        const toggle = checkIn ? event.target : row.querySelector('[data-sc-row-check-in]');
        event.preventDefault();
        if (toggle && !event.repeat) {
            // A row just swapped in is not yet bound.
            htmx.process(toggle);
            toggle.click();
        }
    }
});

// A check-in or a live update replaces the row: the focus goes back to the
// new one.
let playersTableFocus = null;

function rememberPlayersTableFocus() {
    const element = document.activeElement;
    const row = element && element.closest && element.closest('#players-table tbody tr[id^="player-"]');
    if (row) {
        playersTableFocus = {
            id: row.id,
            slot: playersTableFocusSlot(row, element),
            visible: element.matches(':focus-visible'),
        };
    }
}

function restorePlayersTableFocus() {
    if (!playersTableFocus) {
        return;
    }
    const element = document.activeElement;
    if (element && element !== document.body && element.isConnected) {
        playersTableFocus = null;
        return;
    }
    const row = document.getElementById(playersTableFocus.id);
    if (row && !isModalOpened()) {
        focusPlayersTableRow(row, playersTableFocus.slot, playersTableFocus.visible);
    }
    playersTableFocus = null;
}

document.addEventListener('htmx:beforeSwap', rememberPlayersTableFocus);
document.addEventListener('htmx:oobBeforeSwap', rememberPlayersTableFocus);
document.addEventListener('htmx:afterSettle', restorePlayersTableFocus);
document.addEventListener('htmx:oobAfterSwap', restorePlayersTableFocus);
