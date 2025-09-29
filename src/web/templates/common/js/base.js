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
        '/admin/print-view/' +
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

window.addEventListener('request_refresh', function(event) {
    console.log('request_refresh');
    location.reload();
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
