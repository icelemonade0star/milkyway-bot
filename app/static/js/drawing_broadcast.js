(() => {
    "use strict";
    const form = document.getElementById("drawingHashtagReplay"), button = form.querySelector('[type="submit"]');
    const status = document.getElementById("hashtagReplayStatus");
    const setupNotice = document.getElementById("drawingSetupNotice");
    let receiving = !button.disabled, busy = false;
    function setReceiving(enabled) {
        receiving = enabled; button.disabled = busy || !enabled;
        setupNotice.hidden = enabled;
    }
    window.addEventListener("drawing-receiving-state", event => setReceiving(Boolean(event.detail.enabled)));
    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (busy || !receiving) return;
        busy = true; button.disabled = true; status.textContent = "방송 대기열에 추가하고 있어요…";
        try {
            const response = await fetch("/auth/dashboard/drawing/replay", {
                method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({hashtag: document.getElementById("replayHashtag").value.trim()})
            });
            let data = null;
            try { data = await response.json(); } catch { /* JSON이 아닌 오류 응답도 안내한다. */ }
            if (response.status === 403) setReceiving(false);
            if (!response.ok) throw new Error(typeof data?.error === "string" ? data.error :
                typeof data?.detail === "string" ? data.detail : "재생 요청에 실패했어요. 해시태그를 확인하고 다시 시도해주세요.");
            if (!data) throw new Error("재생 응답을 확인하지 못했어요. 다시 시도해주세요.");
            status.textContent = data.already_queued ? "이미 방송 재생 대기 중이거나 재생 중인 그림이에요." :
                "방송 대기열에 추가했어요. OBS 연결 시 순서대로 재생됩니다.";
            window.dispatchEvent(new Event("drawing-queue-changed"));
        } catch (error) { status.textContent = error instanceof Error ? error.message : "재생 요청에 실패했어요."; }
        finally { busy = false; button.disabled = !receiving; }
    });
})();
