function connectOverlaySocket(path, onMessage) {
    let socket = null;
    let retryTimeout = null;
    let retryDelay = 1000;
    let stopped = false;

    function connect() {
        if (stopped) return;
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(`${protocol}//${location.host}${path}`);
        socket.addEventListener("open", () => { retryDelay = 1000; });
        socket.addEventListener("message", (event) => {
            try {
                onMessage(JSON.parse(event.data));
            } catch (error) {
                console.error(error);
            }
        });
        socket.addEventListener("close", () => {
            if (stopped) return;
            retryTimeout = window.setTimeout(connect, retryDelay);
            retryDelay = Math.min(retryDelay * 2, 30000);
        });
    }

    window.addEventListener("pagehide", () => {
        stopped = true;
        window.clearTimeout(retryTimeout);
        socket?.close();
    });
    connect();
}
