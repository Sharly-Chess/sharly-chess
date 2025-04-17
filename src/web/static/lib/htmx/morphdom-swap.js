htmx.defineExtension('morphdom-swap', {
    isInlineSwap: function(swapStyle) {
        return swapStyle === 'morphdom' || swapStyle === 'morphdom-innerHTML' || swapStyle === 'morphdom-outerHTML'
    },
    handleSwap: function(swapStyle, target, fragment, settleInfo) {
        options = {
            onNodeAdded: function (node) {
                if (node.nodeName === 'SCRIPT' && node.src) {
                    var script = document.createElement('script');
                    script.src = node.src;
                    node.replaceWith(script)
                }
            },
            onBeforeElUpdated: function (fromEl, toEl) {
                if (fromEl.nodeName === "SCRIPT" && toEl.nodeName === "SCRIPT") {
                    console.log('onBeforeElUpdated')
                    var script = document.createElement('script');
                    [...toEl.attributes].forEach( attr => { script.setAttribute(attr.nodeName, attr.nodeValue) })
                    script.innerHTML = toEl.innerHTML;
                    fromEl.replaceWith(script)
                    return false;
                }
                return true;
            }
        }
        if (swapStyle === 'morphdom') {
            if (fragment.nodeType === Node.DOCUMENT_FRAGMENT_NODE) {
                morphdom(target, fragment.firstElementChild || fragment.firstChild, options)
                return [target]
            } else {
                morphdom(target, fragment.outerHTML, options)
                return [target]
            }
        }
    }
})
