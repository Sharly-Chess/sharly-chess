function setSize() {
    //  We store the size of the viewport, without the scrollbars, in CSS variables #}
    //  This is necessary since dvh/dwh is broken on Chrome
    let vw = document.documentElement.clientWidth;
    let vh = document.documentElement.clientHeight;
    document.documentElement.style.setProperty('--vw', `${vw}px`);
    document.documentElement.style.setProperty('--vh', `${vh}px`);

    // We store the (dynamic) header height, useful for sticking things under it
    let headerHeight = document.getElementById('top-nav-wrapper')?.offsetHeight ?? 0;
    document.documentElement.style.setProperty('--header-height', `${headerHeight}px`);
}

setSize();

window.addEventListener('resize', setSize);
window.addEventListener('htmx:afterSettle', function () { setSize(); closeTooltips(); });

window.addEventListener("htmx:wsBeforeMessage", function(evt) {
    try {
        const msg = JSON.parse(evt.detail.message);
        if (msg.event) {
            // We intercept websocket events and dispatch them as a custom trigger
            document.body.dispatchEvent(new CustomEvent("ws:" + msg.event,  msg.data || {}));
            evt.preventDefault();
        }
    } catch (e) {
        // not JSON, let htmx handle normally
    }
});

function closeTooltips () {
    $('body .tooltip').remove();
    $('body .tooltip-inner').remove();
    $('body .tooltip-arrow').remove();
}

function closeAirPickers () {
    if (!datePickers) return;
    Object.values(datePickers).forEach((picker) => {
        try {
            if (picker && !picker.isDestroyed) picker.hide();
        } catch (e) {
            // ignore
        }
    });
}

// Enable Bootstrap tooltips cf https://getbootstrap.com/docs/5.3/components/tooltips/
function activateTooltips () {
    if (typeof bootstrap !== 'undefined') {
        tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
        tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
    }
}

function scrollToFirstError() {
    var errorElements = document.querySelectorAll('#modal-wrapper .is-invalid');
    if (errorElements.length > 0) {
        const element = errorElements[0];
        element.scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
        element.select();
        return true;
    }
    return false;
}

window.addEventListener("do_print", function(event) {
    const form = document.createElement('form');
    form.method = 'get';
    form.action = window.location.origin +
        '/document-view/' +
        event.detail.event_uniq_id + '/' +
        event.detail.document;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'options';
    input.value = Object.keys(event.detail.options).map(k => k + '=' + event.detail.options[k]).join('|');
    form.appendChild(input);
    form.target = '_blank';
    document.body.appendChild(form);
    form.submit();
    document.body.removeChild(form);
})

window.addEventListener("download_ready", function () {
    // Workaround for htmx not automatically doing this when redirecting
    // https://github.com/bigskysoftware/htmx/issues/3189
    document.getElementById("please-wait").classList.remove("htmx-request");
});

function renumberPlayerTableRows() {
    var cells = document.querySelectorAll("#players-table .index");
    cells.forEach((cell, i) => {
        cell.textContent = '' + (i + 1);
    });
}

window.addEventListener("renumber_players_and_close_modal", function(event) {
    renumberPlayerTableRows();
    closeModal();
});

window.addEventListener("renumber_players", function(event) {
    renumberPlayerTableRows();
});

window.addEventListener("show.bs.tooltip", function(event) {
    if ($(event.target).hasClass('sidebar-tooltip') && !$('body').hasClass('compact-sidebar')) {
        event.preventDefault();
    }
});

window.addEventListener("show.bs.dropdown", function(event) {
    // Close tooltip when a dropdown is opened
    closeTooltips();
});

const saveState = (element, isOpen) => {
    if (!element.id || element.classList.contains('collapse-state-not-saved')) return;
    const states = JSON.parse(localStorage.getItem('collapseStates') || '{}');
    states[element.id] = isOpen;
    localStorage.setItem('collapseStates', JSON.stringify(states));
};

// Listen globally for Bootstrap collapse show/hide
window.addEventListener('show.bs.collapse', e => saveState(e.target, true));

window.addEventListener('hide.bs.collapse', e => saveState(e.target, false));

const restoreState = () => {
  const states = JSON.parse(localStorage.getItem('collapseStates') || '{}');
  Object.entries(states).forEach(([id, isOpen]) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (isOpen) {
        // Immediately show, bypassing Bootstrap animation
        el.classList.add('show');
        el.style.height = 'auto';
        el.setAttribute('aria-expanded', 'true');
    } else {
        el.classList.remove('show');
        el.style.height = '';
        el.setAttribute('aria-expanded', 'false');
    }
  });
};

$(document).ready(restoreState);

window.addEventListener('htmx:afterSwap', function(event) {
    // Activate the tooltips after a swap
    activateTooltips();
    closeTooltips();
    closeAirPickers();
});

window.addEventListener('htmx:afterSettle', function(event) {
    restoreState();
});


function reloadWithMessagesPreserved() {
    sessionStorage.setItem("preserve_scroll_y", window.scrollY.toString());
    const msgDiv = document.getElementById('messages');
    if (msgDiv) {
        sessionStorage.setItem('preserve_messages_html', msgDiv.innerHTML);
    }
    location.reload();
}

window.addEventListener('request_refresh', () => {
    reloadWithMessagesPreserved();
});

function maybeRemoveMe(elt) {
    var timing = elt.getAttribute('remove-me') || elt.getAttribute('data-remove-me')
    if (timing) {
        setTimeout(function() {
            elt.parentElement.removeChild(elt)
        }, htmx.parseInterval(timing))
    }
}

// After page load, restore
window.addEventListener('DOMContentLoaded', () => {
    const html = sessionStorage.getItem('preserve_messages_html');
    if (html !== null) {
        const msgDiv = document.getElementById('messages');
        if (msgDiv) {
            msgDiv.innerHTML = html;
            // The HTML remove me extension only runs after an HTMX swap. We need to remove the preserved elements
            // after a reload too.
            msgDiv.querySelectorAll('[remove-me],[data-remove-me]').forEach(maybeRemoveMe);
        }
        sessionStorage.removeItem('preserve_messages_html');
    }

    // Restore scroll
    const scrollY = sessionStorage.getItem("preserve_scroll_y");
    if (scrollY !== null) {
        setTimeout(() => {
            window.scrollTo({ top: parseInt(scrollY, 10), behavior: 'instant' });
        }, 0);
        sessionStorage.removeItem("preserve_scroll_y");
    }
});

function debounce(callback, delay){
    var timer;
    return function(){
        var args = arguments;
        var context = this;
        clearTimeout(timer);
        timer = setTimeout(function(){
            callback.apply(context, args);
        }, delay)
    }
}

function toggle_password(event, id) {
    event.preventDefault();
    hide = $(id).attr("type") == 'text'
    $(id).attr('type', hide ? 'password' : 'text');
    $(id + '-toggle-password').addClass(hide ? 'bi-eye-slash-fill' : 'bi-eye-fill');
    $(id + '-toggle-password').removeClass(hide ? 'bi-eye-fill' : 'bi-eye-slash-fill');
}

function toggle_sidebar(e) {
    e.preventDefault();
    const body = $("body");
    if (body.hasClass('compact-sidebar')) {
        body.removeClass('compact-sidebar');
        localStorage.setItem('sidebar-state', 'expanded');
    } else {
        body.addClass('compact-sidebar');
        localStorage.setItem('sidebar-state', 'compact');
    }
}

function errorBeep() {
    var snd = new Audio("/static/sounds/error-beep.wav");
    snd.play();
}

function normalizeText(str) {
    return str
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
}

function init_sidebar() {
    const body = $("body");
    if (body) {
        if (localStorage.getItem('sidebar-state') == 'compact') {
            body.addClass('compact-sidebar');
        } else {
            body.removeClass('compact-sidebar');
        }
    }
}

// Select2

var select2OpenCloseDisabled = false;

$(document).on('select2:opening', '.sharly-chess-select2', function (e) {
    if (select2OpenCloseDisabled) {
        e.preventDefault();
    };
});
$(document).on('select2:close', '.sharly-chess-select2', function (e) {
    if (select2OpenCloseDisabled) {
        e.preventDefault();
    } else {
        var evt = "scroll.select2";
        $(e.target).parents().off(evt);
        $(window).off(evt);
    }
});

// Prevent the dropdown from blinking when deselecting multiple options
$(document).on('select2:unselect', '.sharly-chess-select2', function (e) {
    select2OpenCloseDisabled = true;
    setTimeout(function(){
        select2OpenCloseDisabled = false;
    }, 100);
});

async function downloadFile(el, formId) {
    const url = new URL(el.dataset.exportUrl, window.location.origin);

    if (formId) {
        const form = document.getElementById(formId);
        if (form) {
            const formData = new FormData(form);
            for (const [key, value] of formData.entries()) {
                url.searchParams.append(key, value.toString());
            }
        }
    }

    try {
        const response = await fetch(url, { headers: { 'HX-Request': 'true' } });
        const contentType = response.headers.get('content-type') || '';

        // If server returned a file
        if (contentType.startsWith('application/') || response.headers.get('content-disposition')) {
            // Turn it into a blob for download
            const blob = await response.blob();
            const a = document.createElement('a');
            const downloadUrl = URL.createObjectURL(blob);
            const filename = response.headers
                .get('content-disposition')
                ?.split('filename=')[1]
                ?.replaceAll('"', '') || 'download';
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(downloadUrl);
            return;
        }

        // Allow errors to be displayed
        const html = await response.text();
        const target = response.headers.get('HX-Retarget') || 'body';
        const swapStyle = response.headers.get('HX-Reswap') || 'innerHTML';
        htmx.swap(target, html, { swapStyle });
    } catch (err) {
        console.error('Export failed', err);
        alert('Export failed: ' + err.message);
    }
}

const datePickers = {};

function getAirDatePickerSelectedDates(
    value,
    inputType,
    rangeSeparator,
    valueToDate,
    dateRegex,
    datetimeRegex,
) {
    if (inputType === 'datetime') {
        if (datetimeRegex.test(value)) return [valueToDate(value)];
    } else if (inputType === 'date') {
        if (dateRegex.test(value)) return [valueToDate(value)];
    } else if (inputType === 'date-range') {
        if (dateRegex.test(value)) return [valueToDate(value)];
        if (value.includes(rangeSeparator)) {
            const [start, stop] = value.split(rangeSeparator);
            if (dateRegex.test(start) && dateRegex.test(stop)) {
                return [valueToDate(start), valueToDate(stop)];
            }
        }
    }
    return [];
}

function formatISODate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function setPrintTournamentPlayerSelectOptions(
    playersPerTournamentId,
    optionId,
    documentIds=[],
    addEmptyOption=false,
) {

    const tournamentSelect = $('.modal #tournament');
    const playerSelect = $('.modal #' + optionId);
    function updatePlayers() {
        const tId = parseInt(tournamentSelect.val(), 10);
        const players = playersPerTournamentId[tId] || {};

        playerSelect.empty();
        if (addEmptyOption) {
            playerSelect.append(
                $('<option>', {
                    value: '',
                    text: '-- {{ _("Select player") }} --',
                })
            );
        }

        // Add players
        players.forEach(player => {
            playerSelect.append(
                $('<option>', {
                    value: player.id,
                    text: player.full_name,
                })
            );
            playerSelect.prop('disabled', false);
        });
        playerSelect.trigger('change');
        setTimeout(() => {
            // Waits for the call stack to be cleared (i.e. the end of the `change` event)
            $('.select2-search__field').css('width', '100%');
        }, 0);
    }
    tournamentSelect.on('change', updatePlayers);
    const documentSelect = $('.modal #document');
    if (documentIds.includes(documentSelect.val())){
        updatePlayers();
    } else {
        // wait for the option to be visible to load it
        documentSelect.on('change', function () {
            if (
                documentIds.includes($(this).val()) &&
                playerSelect.children().length === 0
            ) {
                updatePlayers();
            }
        });
    }
}

function setPrintTournamentTeamSelectOptions(
    teamsPerTournamentId,
    optionId,
    documentIds=[],
) {
    const tournamentSelect = $('.modal #tournament');
    const teamSelect = $('.modal #' + optionId);
    function updateTeams() {
        const tId = parseInt(tournamentSelect.val(), 10);
        const teams = teamsPerTournamentId[tId] || [];

        teamSelect.empty();
        teams.forEach(team => {
            teamSelect.append(
                $('<option>', {
                    value: team.id,
                    text: team.name,
                })
            );
            teamSelect.prop('disabled', false);
        });
        teamSelect.trigger('change');
        setTimeout(() => {
            $('.select2-search__field').css('width', '100%');
        }, 0);
    }
    tournamentSelect.on('change', updateTeams);
    const documentSelect = $('.modal #document');
    if (documentIds.includes(documentSelect.val())) {
        updateTeams();
    } else {
        documentSelect.on('change', function () {
            if (
                documentIds.includes($(this).val()) &&
                teamSelect.children().length === 0
            ) {
                updateTeams();
            }
        });
    }
}

var refreshMessagesIgnored = 0;
function getIsNextRefreshMessageIgnored() {
    if (refreshMessagesIgnored > 0) {
        refreshMessagesIgnored -= 1;
        return true;
    }
    return false;
}
