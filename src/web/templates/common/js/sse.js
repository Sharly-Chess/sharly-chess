(function() {
    // Store the real EventSource only in the leader tab
    let isLeader = false;
    let es = null;
    const bc = new BroadcastChannel("sharly-sse");

    function ensureLeader(url) {
        if (isLeader) return;
        isLeader = true;

        es = new EventSource(url, { withCredentials: true });
        console.log("[SSE] Leader opened EventSource");

        es.onmessage = (msg) => {
            try {
                console.log("[SSE] Leader Received", msg.data);
                const parsed = JSON.parse(msg.data);
                bc.postMessage(parsed);
            } catch (err) {
                console.error("Bad SSE payload", err, msg.data);
            }
        };

        es.onerror = (err) => console.error("[SSE] error", err);

        window.addEventListener("beforeunload", () => {
            if (es) {
                es.close();
                bc.postMessage({ type: "leader-left" });
            }
        });
    }

    // Override HTMX’s EventSource creation
    htmx.createEventSource = function(url) {
        console.log("[SSE] Creating EventSource", url);
        // Instead of returning a real EventSource,
        // return a "virtual EventSource" implemented with EventTarget
        const fake = new EventTarget();

        // Start listening for broadcasted messages
        bc.onmessage = (msg) => {
            console.log("[SSE] Received", msg);
            const { event, data, type } = msg.data || {};
            if (type === "leader-left" && !isLeader) {
                ensureLeader(url);
                return;
            }
            if (event) {
                console.log("Broadcasting", event, data);
                fake.dispatchEvent(new MessageEvent(event, { data }));
            }
        };

        // Make sure someone is the leader
        bc.postMessage({ type: "hello" });
        setTimeout(() => {
            if (!isLeader) ensureLeader(url);
        }, 200);

    return fake;
    };
})();
