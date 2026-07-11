const timerOverlay = document.getElementById("timerOverlay");
const timerTitle = document.getElementById("timerTitle");
const timerTime = document.getElementById("timerTime");
const config = JSON.parse(document.getElementById("timerOverlayConfig").textContent);
const isPreview = new URLSearchParams(location.search).has("preview");
const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
const socket = new WebSocket(`${wsProtocol}//${location.host}${config.websocket_path}`);
let options = config.options || {};
let timerState = null;
let timerFrame = null;
let autoDeleteTimeout = null;

function formatTimerTime(ms) {
    const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) {
        return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function currentTimerRemaining() {
    if (!timerState) {
        return 0;
    }
    if (timerState.running && timerState.ends_at_ms) {
        return Math.max(0, timerState.ends_at_ms - Date.now());
    }
    return Math.max(0, Number(timerState.remaining_ms) || 0);
}

function stopTimerFrame() {
    if (timerFrame) {
        window.cancelAnimationFrame(timerFrame);
        timerFrame = null;
    }
}

function stopAutoDeleteTimer() {
    if (autoDeleteTimeout) {
        window.clearTimeout(autoDeleteTimeout);
        autoDeleteTimeout = null;
    }
}

function scheduleAutoDelete() {
    if (!options.timer_auto_delete || autoDeleteTimeout) {
        return;
    }
    const delaySeconds = Math.max(0, Number(options.timer_auto_delete_delay_seconds) || 0);
    autoDeleteTimeout = window.setTimeout(() => {
        autoDeleteTimeout = null;
        timerState = null;
        renderTimer();
    }, delaySeconds * 1000);
}

function renderTimer() {
    if (!timerState) {
        timerOverlay.classList.remove("is-visible");
        stopTimerFrame();
        stopAutoDeleteTimer();
        return;
    }

    const remaining = currentTimerRemaining();
    timerTitle.textContent = timerState.title || "타이머";
    timerTime.textContent = formatTimerTime(remaining);
    timerOverlay.classList.add("is-visible");
    timerOverlay.classList.toggle("is-done", remaining <= 0);

    if (timerState.running && remaining > 0) {
        stopAutoDeleteTimer();
        timerFrame = window.requestAnimationFrame(renderTimer);
    } else {
        timerState.running = false;
        stopTimerFrame();
        if (remaining <= 0) {
            scheduleAutoDelete();
        } else {
            stopAutoDeleteTimer();
        }
    }
}

function handleTimerEvent(payload) {
    if (payload.options) {
        options = {...options, ...payload.options};
    }
    if (payload.action === "delete") {
        timerState = null;
        stopAutoDeleteTimer();
        renderTimer();
        return;
    }
    if (!payload.timer) {
        return;
    }
    timerState = payload.timer;
    stopTimerFrame();
    stopAutoDeleteTimer();
    renderTimer();
}

socket.addEventListener("message", (event) => {
    try {
        const payload = JSON.parse(event.data);
        if (payload.type === "timer") {
            handleTimerEvent(payload);
        }
    } catch (error) {
        console.error(error);
    }
});

window.addEventListener("message", (event) => {
    if (!isPreview || event.origin !== window.location.origin) {
        return;
    }
    if (event.data?.type === "milkyway-overlay-sample-timer") {
        handleTimerEvent(event.data.payload);
    }
});
