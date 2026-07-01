function isTargetInput(target) {
    let isTextInput = target.tagName === "INPUT" && !["checkbox", "radio", "range", "button", "file", "reset", "submit", "color"].includes(target.type);
    return target.isContentEditable || (isTextInput || target.tagName === "TEXTAREA" || target.tagName === "SELECT") && !target.readOnly;
}

function keyboardShortcutManager(event) {

    if (event.repeat) {return;}
    if (isModalOpened()) {return;}
    if (isTargetInput(event.target)) {return;}

    let navigationShortcuts = {
        'a': "SC_A",
        'c': "SC_C",
        'd': "SC_D",
        'i': "SC_I",
        'j': "SC_J",
        'l': "SC_L",
        'm': "SC_M",
        'p': "SC_P",
        'r': "SC_R",
        's': "SC_S",
        't': "SC_T",
        'x': "SC_X",
        'z': "SC_Z",
    }

    let key = event.key.toLowerCase()

    switch(key) {
        case '+':
            if (event.ctrlKey || event.altKey) {
                break
            }
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

        default:
            if (Object.keys(navigationShortcuts).includes(key) && !event.shiftKey && !event.ctrlKey && !event.altKey) {
                document.body.dispatchEvent(new CustomEvent(navigationShortcuts[key]));
            }
            break

    }

}

window.addEventListener("keydown", keyboardShortcutManager);
