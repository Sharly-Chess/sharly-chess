
function closeModal() {
    var myModalEl = document.getElementById('modal-wrapper');
    var modal = bootstrap.Modal.getInstance(myModalEl);
    if (modal) {
        modal.hide();
    }
    closeTooltips();
}

window.addEventListener('show.bs.modal', function(event) {
    var target = $(event.relatedTarget);
    if (!target) return;

    // After a modal closes, bootstrap refocusses the element causing the tooltip to reopen.
    // We disable the tooltip until the button loses focus.
    target.one("focus", function(event) {
        var parent = target.closest('*[data-bs-toggle="tooltip"]')
        if (parent) {
            parent.tooltip('disable');
            target.one('blur mouseover', function() {
                parent.tooltip('enable');
                target.blur();
                target.focus();
            })
        }

    })
});

function modalIsClosed() {
    return !document.getElementById('modal-wrapper').classList.contains('show');
}

function handleModalOpened(static) {
    var modal = bootstrap.Modal.getOrCreateInstance('#modal-wrapper', {});

    // This is a hack to force the modal to be static
    // https://github.com/twbs/bootstrap/issues/35664
    // https://github.com/twbs/bootstrap/issues/35664#issuecomment-1028179994
    modal._config.backdrop = static ? 'static' : true;
    modal._config.keyboard = static ? false : true;

    if (modalIsClosed()) {
        // The modal is usually opened at this point, following a user action,
        // but this allows us to force open a modal from the server.
        modal.show();
    }

    closeTooltips();
    activateTooltips();
    scrollToFirstError();
}

window.addEventListener("modal_opened", function(event) {
    handleModalOpened(false);
});

window.addEventListener("static_modal_opened", function(event) {
    handleModalOpened(true);
});

window.addEventListener("close_modal", function(event) {
    closeModal()
});

let ignoreNextModalClose = false;
var refreshRequested = false;

function requestRefresh() {
    refreshRequested = true;
}

// Intercept Bootstrap modal hide
$(document).on('hide.bs.modal', function (e) {
    if (ignoreNextModalClose) {
        e.stopImmediatePropagation();
        e.preventDefault();
        ignoreNextModalClose = false;
    } else if (refreshRequested) {
        e.preventDefault();
        document.body.dispatchEvent(new CustomEvent('request_refresh'));
        refreshRequested = false;
    }
});

function preparePrintModal(print_document_id, tournament_id, print_round) {
    default_print_document_id = print_document_id || '';
    default_print_tournament_id = tournament_id || '';
    default_print_round = print_round || '';
}
