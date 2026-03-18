function isTargetInput(target) {
    let isTextInput = target.tagName === "INPUT" && !["checkbox", "radio", "range", "button", "file", "reset", "submit", "color"].includes(target.type);
    return target.isContentEditable || (isTextInput || target.tagName === "TEXTAREA" || target.tagName === "SELECT") && !target.readOnly;
}

function isModalOpened() {
    return document.getElementById('modal-wrapper').classList.contains('show');
}

function keyboardShortcutManager(event) {

    if (event.repeat) {return;}
    if (isModalOpened()) {return;}
    if (isTargetInput(event.target)) {return;}

    switch(event.key.toLowerCase()) {
        case '+': 
            document.body.dispatchEvent(new CustomEvent("SC_Plus"));
            break;

        case 'arrowleft': 
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_ArrowLeft"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_ArrowLeft"));
            break;

        case 'arrowright': 
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_ArrowRight"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_ArrowRight"));
            break;

        case 'pageup': 
            document.body.dispatchEvent(new CustomEvent("SC_PageUp"));
            break;

        case 'pagedown': 
            document.body.dispatchEvent(new CustomEvent("SC_PageDown"));
            break;

        case 't':
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_T"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_T"));
            break;

        case 'c':
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_C"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_C"));
            break;

        case 'p':
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_P"));
                break;
            }
            if (event.altKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Alt_P"));
                event.preventDefault();
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_P"));
            break;

        case 'j':
            document.body.dispatchEvent(new CustomEvent("SC_J"));
            break;

        case 'a':
            document.body.dispatchEvent(new CustomEvent("SC_A"));
            break;

        case 's':
            document.body.dispatchEvent(new CustomEvent("SC_S"));
            break;

        case 'f':
            document.body.dispatchEvent(new CustomEvent("SC_F"));
            break;

        case 'r':
            document.body.dispatchEvent(new CustomEvent("SC_R"));
            break;

        case 'd':
            document.body.dispatchEvent(new CustomEvent("SC_D"));
            break;
            
        default:
            break

    }

}

window.addEventListener("keydown", keyboardShortcutManager);
