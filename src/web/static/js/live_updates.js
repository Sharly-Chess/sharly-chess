// Live updates: when check-ins or results change, the tab holding a
// #live-update element asks the server what the change brings to it and
// applies it in place, row by row. The messages of a burst are gathered into
// one request, and nothing is applied while the arbiter is in the middle of
// something.

const LIVE_UPDATE_DELAY = 300;
const LIVE_UPDATE_RETRY_DELAY = 1000;
const LIVE_UPDATE_FLASH_DURATION = 2400;

// The ways to apply an update, by the value of data-live-update.
const liveUpdateAppliers = {};

let liveUpdateChanges = newLiveUpdateChanges();
let liveUpdateTimer = null;
let liveUpdateRunning = false;
let liveUpdateEvents = [];
let livePointerIsDown = false;

// The rows left as they are until a time, by element id: a check-in made in
// the players table counts down on its row before the row follows it.
const liveUpdateHolds = new Map();

function newLiveUpdateChanges() {
    return {all: false, playerIds: new Set(), boardIds: new Set()};
}

function holdLiveUpdate(elementId, duration) {
    liveUpdateHolds.set(elementId, Date.now() + duration);
}

function liveUpdateIsHeld(element) {
    const until = liveUpdateHolds.get(element.id);
    if (until === undefined) {
        return false;
    }
    if (until > Date.now()) {
        return true;
    }
    liveUpdateHolds.delete(element.id);
    return false;
}

window.addEventListener('pointerdown', () => { livePointerIsDown = true; }, true);
window.addEventListener('pointerup', () => { livePointerIsDown = false; }, true);
window.addEventListener('pointercancel', () => { livePointerIsDown = false; }, true);

function arbiterIsBusy() {
    const focused = document.activeElement;
    return !modalIsClosed()
        || livePointerIsDown
        || document.querySelector(
            '.dropdown-menu.show, .select2-container--open, .popover, .sortable-chosen, .htmx-request'
        ) !== null
        || (focused !== null && focused.matches(
            'textarea, select, [contenteditable], input:not([type=search])'
        ))
        || window.getSelection().toString() !== ''
        || (typeof keyQueue !== 'undefined' && keyQueue.length > 0);
}

function scheduleLiveUpdate(delay) {
    clearTimeout(liveUpdateTimer);
    liveUpdateTimer = setTimeout(runLiveUpdate, delay);
}

function onLiveUpdateMessage(event) {
    const detail = event.detail || {};
    if (!Array.isArray(detail.player_ids)) {
        liveUpdateChanges.all = true;
    } else {
        detail.player_ids.forEach((id) => liveUpdateChanges.playerIds.add(id));
        (detail.board_ids || []).forEach((id) => liveUpdateChanges.boardIds.add(id));
    }
    scheduleLiveUpdate(LIVE_UPDATE_DELAY);
}

function requeueLiveUpdateChanges(changes) {
    liveUpdateChanges.all ||= changes.all;
    changes.playerIds.forEach((id) => liveUpdateChanges.playerIds.add(id));
    changes.boardIds.forEach((id) => liveUpdateChanges.boardIds.add(id));
    scheduleLiveUpdate(LIVE_UPDATE_RETRY_DELAY);
}

async function runLiveUpdate() {
    const source = document.getElementById('live-update');
    const apply = source && liveUpdateAppliers[source.dataset.liveUpdate];
    if (!apply) {
        liveUpdateChanges = newLiveUpdateChanges();
        return;
    }
    // A hidden page is updated once seen again, so that what changed lights
    // up in front of the arbiter.
    if (document.visibilityState !== 'visible') {
        document.addEventListener(
            'visibilitychange', () => scheduleLiveUpdate(LIVE_UPDATE_DELAY), {once: true}
        );
        return;
    }
    if (liveUpdateRunning || arbiterIsBusy()) {
        scheduleLiveUpdate(LIVE_UPDATE_RETRY_DELAY);
        return;
    }
    const changes = liveUpdateChanges;
    liveUpdateChanges = newLiveUpdateChanges();
    liveUpdateRunning = true;
    try {
        if (!await apply(source, changes)) {
            requeueLiveUpdateChanges(changes);
        }
    } catch (error) {
        console.warn('Live update failed', error);
    } finally {
        liveUpdateRunning = false;
    }
}

// The answer of the server to a live update, parsed, or null when the page
// moved on meanwhile.
async function fetchLiveUpdate(source, body) {
    const response = await fetch(source.dataset.url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'HX-Request': 'true'},
        body: JSON.stringify(body),
    });
    if (!response.ok || !source.isConnected) {
        return null;
    }
    const html = await response.text();
    return source.isConnected ? new DOMParser().parseFromString(html, 'text/html') : null;
}

function disposeTooltipsOf(node) {
    if (typeof bootstrap === 'undefined') {
        return;
    }
    [node, ...node.querySelectorAll(tooltipSelector)].forEach((element) => {
        bootstrap.Tooltip.getInstance(element)?.dispose();
    });
}

// What a row shows, without what the browser added to it since it came in.
function liveRowSignature(row) {
    const copy = row.cloneNode(true);
    [copy, ...copy.querySelectorAll('*')].forEach((element) => {
        ['aria-describedby', 'aria-label', 'data-bs-original-title'].forEach(
            (name) => element.removeAttribute(name)
        );
        element.classList.remove('live-updated');
        if (element.getAttribute('class') === '') {
            element.removeAttribute('class');
        }
    });
    return copy.outerHTML;
}

function flashLiveUpdated(elements) {
    elements.forEach((element) => {
        element.classList.add('live-updated');
        setTimeout(() => element.classList.remove('live-updated'), LIVE_UPDATE_FLASH_DURATION);
    });
}

// The first row at the top of the window and where it stands, so that the
// rows that come or go above it do not move it.
function liveScrollAnchor(rows) {
    const top = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--header-height')
    ) || 0;
    const row = rows.find((element) => element.getBoundingClientRect().bottom > top);
    return row ? {row: row, top: row.getBoundingClientRect().top} : null;
}

function restoreLiveScrollAnchor(anchor) {
    if (anchor && anchor.row.isConnected) {
        window.scrollBy(0, anchor.row.getBoundingClientRect().top - anchor.top);
    }
}

// Players tab: the rows follow the filters and the order of the table as far
// down as the page has loaded; only the rows the page lacks or whose players
// changed are sent.
liveUpdateAppliers.players = async (source, changes) => {
    const table = document.getElementById('players-table');
    if (!table) {
        return true;
    }
    const pages = () => [...table.querySelectorAll(':scope > tbody[data-page]')];
    const rows = () => [...table.querySelectorAll(':scope > tbody[data-page] > tr[id^="player-"]')];
    const shownIds = rows().map((row) => row.id);
    const loadedPages = pages().length;
    const fresh = await fetchLiveUpdate(source, {
        shown_player_ids: shownIds.map((id) => Number(id.slice('player-'.length))),
        changed_player_ids: changes.all ? null : [...changes.playerIds],
        loaded_pages: loadedPages,
        complete: !pages().at(-1)?.hasAttribute('hx-get'),
    });
    if (!fresh || !table.isConnected) {
        return true;
    }
    // The arbiter started something, or the table moved on (a page scrolled
    // in, a row changed by hand): the update is asked for again.
    const current = rows();
    if (
        arbiterIsBusy()
        || pages().length !== loadedPages
        || current.map((row) => row.id).join() !== shownIds.join()
    ) {
        return false;
    }

    const order = JSON.parse(fresh.getElementById('players-live-order').textContent)
        .map((id) => `player-${id}`);
    const freshRows = new Map(
        [...fresh.getElementById('players-live-rows').content.children]
            .map((row) => [row.id, row])
    );
    const currentRows = new Map(current.map((row) => [row.id, row]));
    const anchor = liveScrollAnchor(current);
    const added = [];
    const placed = [];
    order.forEach((id) => {
        const existing = currentRows.get(id);
        const replacement = freshRows.get(id);
        if (!replacement || (existing && liveUpdateIsHeld(existing))) {
            if (existing) {
                placed.push(existing);
            }
            return;
        }
        if (existing && liveRowSignature(existing) === liveRowSignature(replacement)) {
            placed.push(existing);
            return;
        }
        const row = document.importNode(replacement, true);
        placed.push(row);
        added.push(row);
    });
    // A held row the filters no longer keep stays where it was until its
    // own countdown takes it away.
    const kept = new Set(placed);
    current.forEach((row, index) => {
        if (!kept.has(row) && liveUpdateIsHeld(row)) {
            placed.splice(Math.min(index, placed.length), 0, row);
            kept.add(row);
        }
    });
    current.forEach((row) => {
        if (!kept.has(row)) {
            disposeTooltipsOf(row);
            row.remove();
        }
    });

    const pageSize = Number(source.dataset.pageSize);
    const tbodies = pages();
    tbodies.forEach((tbody, index) => {
        const last = index === tbodies.length - 1;
        tbody.append(...placed.slice(index * pageSize, last ? undefined : (index + 1) * pageSize));
    });

    added.forEach((row) => {
        htmx.process(row);
        activateTooltips(row);
    });
    renumberPlayerTableRows();
    const counters = document.getElementById('players-table-counters');
    if (counters) {
        counters.textContent = fresh.getElementById('players-live-counters').textContent;
    }
    const emptyRow = document.getElementById('players-table-empty-row');
    const freshEmptyRow = fresh.getElementById('players-live-empty-row').content.firstElementChild;
    if (emptyRow && freshEmptyRow && emptyRow.innerHTML.trim() !== freshEmptyRow.innerHTML.trim()) {
        const row = document.importNode(freshEmptyRow, true);
        emptyRow.replaceWith(row);
        htmx.process(row);
    }
    restoreLiveScrollAnchor(anchor);
    flashLiveUpdated(added);
    return true;
};

htmx.onLoad(function () {
    const source = document.getElementById('live-update');
    const events = source ? source.dataset.events.split(' ') : [];
    if (events.join() === liveUpdateEvents.join()) {
        return;
    }
    liveUpdateEvents.forEach((name) => document.body.removeEventListener(name, onLiveUpdateMessage));
    liveUpdateEvents = events;
    liveUpdateEvents.forEach((name) => document.body.addEventListener(name, onLiveUpdateMessage));
});
