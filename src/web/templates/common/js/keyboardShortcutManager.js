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
                if (event.ctrlKey) {
                    document.body.dispatchEvent(new CustomEvent("SC_Ctrl_Shift_ArrowLeft"));
                    break;
                }
                document.body.dispatchEvent(new CustomEvent("SC_Shift_ArrowLeft"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_ArrowLeft"));
            break;

        case 'arrowright':
            if (event.shiftKey) {
                if (event.ctrlKey) {
                    document.body.dispatchEvent(new CustomEvent("SC_Ctrl_Shift_ArrowRight"));
                    break;
                }
                document.body.dispatchEvent(new CustomEvent("SC_Shift_ArrowRight"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_ArrowRight"));
            break;

        case 'arrowup':
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_ArrowUp"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_ArrowUp"));
            break;

        case 'arrowdown':
            if (event.shiftKey) {
                document.body.dispatchEvent(new CustomEvent("SC_Shift_ArrowDown"));
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_ArrowDown"));
            break;

        case 't':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_T"));
            break;

        case 'c':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_C"));
            break;

        case 'p':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_P"));
            break;

        case 'j':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_J"));
            break;

        case 'a':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_A"));
            break;

        case 's':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_S"));
            break;

        case 'f':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_F"));
            break;

        case 'r':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_R"));
            break;

        case 'd':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_D"));
            break;

        case 'm':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_M"));
            break;

        case 'l':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_L"));
            break;

        case 'x':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_X"));
            break;

        case 'z':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_Z"));
            break;

        case 'i':
            if (event.ctrlKey) {
                break;
            }
            document.body.dispatchEvent(new CustomEvent("SC_I"));
            break;

        default:
            break

    }

}

window.addEventListener("keydown", keyboardShortcutManager);
