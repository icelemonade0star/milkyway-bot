const timerOverlay = document.getElementById("timerOverlay");
const timerTitle = document.getElementById("timerTitle");
const timerTime = document.getElementById("timerTime");
const config = JSON.parse(document.getElementById("timerOverlayConfig").textContent);
const isPreview = new URLSearchParams(location.search).has("preview");
let options = config.options || {};
let timerState = null;
let timerReceivedAt = 0;
let timerFrame = null;
let autoDeleteTimeout = null;
let hiddenTimerId = null;
const AUTO_DELETE_FADE_MS = 600;

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
    if (timerState.running) {
        return Math.max(0, timerState.remaining_ms - (performance.now() - timerReceivedAt));
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
    timerOverlay.classList.remove("is-fading");
}

function scheduleAutoDelete() {
    if (!options.timer_auto_delete || autoDeleteTimeout) {
        return;
    }
    const delaySeconds = Math.max(0, Number(options.timer_auto_delete_delay_seconds) || 0);
    autoDeleteTimeout = window.setTimeout(() => {
        timerOverlay.classList.add("is-fading");
        autoDeleteTimeout = window.setTimeout(() => {
            autoDeleteTimeout = null;
            hiddenTimerId = timerState?.timer_id || null;
            timerState = null;
            renderTimer();
        }, AUTO_DELETE_FADE_MS);
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
        timerState.remaining_ms = remaining;
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
    if (payload.action === "sync" && payload.timer.timer_id && (
        payload.timer.timer_id === hiddenTimerId ||
        (payload.timer.timer_id === timerState?.timer_id && currentTimerRemaining() <= 0 &&
            payload.timer.remaining_ms <= 0)
    )) {
        return;
    }
    hiddenTimerId = null;
    timerState = {
        ...payload.timer,
        remaining_ms: Math.max(0, Number(payload.timer.remaining_ms) || 0),
    };
    timerReceivedAt = performance.now();
    stopTimerFrame();
    stopAutoDeleteTimer();
    renderTimer();
}

if (!isPreview) {
    connectOverlaySocket(config.websocket_path, (payload) => {
        if (payload.type === "overlay-settings") {
            document.getElementById("overlayCustomStyle").textContent = payload.custom_css;
            const changed = options.timer_auto_delete !== payload.options.timer_auto_delete ||
                options.timer_auto_delete_delay_seconds !== payload.options.timer_auto_delete_delay_seconds;
            options = {...options, ...payload.options};
            if (changed) {
                stopAutoDeleteTimer();
                stopTimerFrame();
                renderTimer();
            }
            return;
        }
        if (payload.type === "timer") {
            handleTimerEvent(payload);
        }
    });
}

window.addEventListener("message", (event) => {
    if (!isPreview || event.origin !== window.location.origin) {
        return;
    }
    if (event.data?.type === "milkyway-overlay-sample-timer") {
        handleTimerEvent(event.data.payload);
    }
});
