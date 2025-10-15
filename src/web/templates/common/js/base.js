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
        errorElements[0].scrollIntoView({
            behavior: "smooth",
            block: "start",
        });
    }
}

window.addEventListener("do_print", function(event) {
    closeModal();
    const form = document.createElement('form');
    form.method = 'get';
    form.action = window.location.origin +
        '/print-view/' +
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

window.addEventListener("renumber_players_and_close_modal", function(event) {
    var cells = document.querySelectorAll("#players-table th.index");
    cells.forEach((cell, i) => {
        cell.textContent = '' + (i + 1);
    });
    closeModal();
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

const saveState = (id, isOpen) => {
    const states = JSON.parse(localStorage.getItem('collapseStates') || '{}');
    states[id] = isOpen;
    localStorage.setItem('collapseStates', JSON.stringify(states));
};

// Listen globally for Bootstrap collapse show/hide
window.addEventListener('show.bs.collapse', e => {
    if (e.target.id) saveState(e.target.id, true);
});

window.addEventListener('hide.bs.collapse', e => {
    if (e.target.id) saveState(e.target.id, false);
});

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
});

window.addEventListener('htmx:afterSettle', function(event) {
    restoreState();
});


function reloadWithMessagesPreserved() {
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
