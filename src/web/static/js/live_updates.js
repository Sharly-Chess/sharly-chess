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
    return {all: false, checkIns: false, playerIds: new Set(), boardIds: new Set()};
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
        || document.querySelector('tr.highlight-warning') !== null
        || (typeof keyQueue !== 'undefined' && keyQueue.length > 0)
        || (typeof requestInFlight !== 'undefined' && requestInFlight === true);
}

function scheduleLiveUpdate(delay) {
    clearTimeout(liveUpdateTimer);
    liveUpdateTimer = setTimeout(runLiveUpdate, delay);
}

function onLiveUpdateMessage(event) {
    const detail = event.detail || {};
    // After a reconnection anything may have changed.
    if (event.type.startsWith('ws:new-checkins') || event.type === 'ws:reconnected') {
        liveUpdateChanges.checkIns = true;
    }
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
    liveUpdateChanges.checkIns ||= changes.checkIns;
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

    // Only the rows out of place are moved: moving the others would have
    // the browser lay the whole table out again, which on a large table
    // takes long enough to be felt.
    const pageSize = Number(source.dataset.pageSize);
    const tbodies = pages();
    tbodies.forEach((tbody, index) => {
        const last = index === tbodies.length - 1;
        let previous = null;
        placed.slice(index * pageSize, last ? undefined : (index + 1) * pageSize).forEach((row) => {
            const expected = previous
                ? previous.nextElementSibling
                : tbody.querySelector(':scope > tr[id^="player-"]');
            if (row !== expected) {
                if (previous) {
                    previous.after(row);
                } else if (expected) {
                    expected.before(row);
                } else {
                    tbody.append(row);
                }
            }
            previous = row;
        });
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

// Pairings tab: the rows of the boards whose results changed are put in
// place, with the controls, the column of the players to pair and the reason
// the round cannot be paired around them; the boards the "In play" filter no
// longer keeps are taken away. When the change cannot be put in place, the
// tab is loaded again where it stood.
liveUpdateAppliers.pairings = async (source, changes) => {
    const boardRows = () => [...document.querySelectorAll('#main-wrapper tr[data-board-id]')];
    const shownIds = boardRows().map((row) => Number(row.dataset.boardId));
    const fresh = await fetchLiveUpdate(source, {
        shown_board_ids: shownIds,
        changed_board_ids: changes.all ? null : [...changes.boardIds],
        changed_player_ids: changes.all ? null : [...changes.playerIds],
        check_ins_changed: changes.checkIns,
        has_unpaired: document.getElementById('pairings-sidebar') !== null,
    });
    if (!fresh) {
        return true;
    }
    if (
        arbiterIsBusy()
        || boardRows().map((row) => Number(row.dataset.boardId)).join() !== shownIds.join()
    ) {
        return false;
    }
    const live = fresh.getElementById('pairings-live');
    if (live.dataset.action === 'reload') {
        const scrollY = window.scrollY;
        await htmx.ajax('GET', source.dataset.tabUrl, {target: 'body', swap: 'innerHTML'});
        window.scrollTo(0, scrollY);
        return true;
    }
    const anchor = liveScrollAnchor(boardRows());
    JSON.parse(live.dataset.removedBoardIds).forEach((id) => {
        document.querySelectorAll(`#main-wrapper tr[data-board-id="${id}"]`).forEach((row) => {
            disposeTooltipsOf(row);
            row.remove();
        });
    });
    // The rows replaced lose the board the keyboard is on, and light up only
    // when what they show changed.
    const highlighted = [...document.querySelectorAll('#main-wrapper tr.highlight[id]')].map((row) => row.id);
    const updatedIds = JSON.parse(live.dataset.updatedBoardIds);
    const signatures = new Map(updatedIds.map((id) => {
        const row = document.querySelector(`#main-wrapper tr[data-board-id="${id}"]`);
        return [id, row ? liveRowSignature(row) : null];
    }));
    boardRows()
        .filter((row) => updatedIds.includes(Number(row.dataset.boardId)))
        .forEach(disposeTooltipsOf);
    htmx.swap(source, fresh.body.innerHTML, {swapStyle: 'innerHTML'});
    highlighted.forEach((id) => document.getElementById(id)?.classList.add('highlight'));
    const flashed = updatedIds
        .map((id) => document.querySelector(`#main-wrapper tr[data-board-id="${id}"]`))
        .filter((row) => row && liveRowSignature(row) !== signatures.get(Number(row.dataset.boardId)));
    activateTooltips(document.getElementById('main-wrapper'));
    restoreLiveScrollAnchor(anchor);
    flashLiveUpdated(flashed);
    document.dispatchEvent(new CustomEvent('live-update'));
    return true;
};

htmx.onLoad(function () {
    const source = document.getElementById('live-update');
    const events = source ? [...source.dataset.events.split(' '), 'ws:reconnected'] : [];
    if (events.join() === liveUpdateEvents.join()) {
        return;
    }
    liveUpdateEvents.forEach((name) => document.body.removeEventListener(name, onLiveUpdateMessage));
    liveUpdateEvents = events;
    liveUpdateEvents.forEach((name) => document.body.addEventListener(name, onLiveUpdateMessage));
});

// A screen listens to the events of its event on a socket of its own, which
// lives as long as the screen is shown: the refreshes of a screen replace the
// whole body, and the screen page can be left for another page with a socket
// of its own.
let screenSocket = null;
let screenSocketUrl = null;
let screenSocketTimer = null;
let screenSocketRetryDelay = 1000;

function syncScreenSocket() {
    const url = document.getElementById('screen-live-update')?.dataset.wsUrl || null;
    if (url === screenSocketUrl) {
        return;
    }
    clearTimeout(screenSocketTimer);
    const socket = screenSocket;
    screenSocket = null;
    socket?.close();
    screenSocketUrl = url;
    screenSocketRetryDelay = 1000;
    if (url) {
        openScreenSocket(false);
    }
}

function openScreenSocket(reconnecting) {
    const url = new URL(screenSocketUrl, window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(url);
    screenSocket = socket;
    socket.addEventListener('open', () => {
        screenSocketRetryDelay = 1000;
        if (reconnecting) {
            document.body.dispatchEvent(new CustomEvent('ws:reconnected'));
        }
    });
    socket.addEventListener('message', (message) => dispatchWsMessage(message.data));
    socket.addEventListener('close', () => {
        if (screenSocket !== socket) {
            return;
        }
        screenSocket = null;
        screenSocketTimer = setTimeout(() => openScreenSocket(true), screenSocketRetryDelay);
        screenSocketRetryDelay = Math.min(screenSocketRetryDelay * 2, 30000);
    });
}

htmx.onLoad(syncScreenSocket);
