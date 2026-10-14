(() => {
    "use strict";
    const form = document.getElementById("drawingSettings"), status = document.getElementById("settingsStatus");
    const preview = document.getElementById("drawingPreview");
    function options() {
        return Object.fromEntries(Array.from(form.elements).filter(item => item.name).map(item => [item.name,
            item.type === "checkbox" ? item.checked : Number(item.value)]));
    }
    function test() { preview.contentWindow.postMessage({type: "drawing-demo", options: options()}, location.origin); }
    let savedOptions = options();
    const dirtyNotice = document.getElementById("drawingSettingsDirty");
    function dirty() { return JSON.stringify(options()) !== JSON.stringify(savedOptions); }
    function updateDirty() { dirtyNotice.hidden = !dirty(); }
    form.addEventListener("input", updateDirty);
    form.addEventListener("change", updateDirty);
    window.addEventListener("pageshow", updateDirty);
    window.addEventListener("beforeunload", event => {
        if (dirty()) { event.preventDefault(); event.returnValue = ""; }
    });
    document.getElementById("testDrawing").addEventListener("click", test);
    form.addEventListener("submit", async event => {
        event.preventDefault(); status.textContent = "설정을 저장하고 있어요…";
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        const submitted = options();
        try {
            const response = await fetch("/auth/dashboard/drawing", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(submitted)});
            const data = await response.json();
            if (!response.ok) throw new Error(typeof data.error === "string" ? data.error :
                typeof data.detail === "string" ? data.detail : "설정 저장에 실패했습니다.");
            status.textContent = "설정을 저장했어요."; test();
            savedOptions = data.options || submitted; updateDirty();
            window.dispatchEvent(new CustomEvent("drawing-settings-saved", {detail: savedOptions}));
        } catch (error) { status.textContent = error.message; }
        finally { button.disabled = false; }
    });
    const copyTimers = new WeakMap();
    document.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
        const input = document.getElementById(button.dataset.copy);
        const copyStatus = document.getElementById(`${button.dataset.copy}Status`);
        const label = button.dataset.copyLabel || (button.dataset.copyLabel = button.textContent);
        clearTimeout(copyTimers.get(button));
        button.disabled = true;
        try {
            await navigator.clipboard.writeText(input.value);
            copyStatus.textContent = "링크를 복사했어요."; button.textContent = "복사했어요";
            copyTimers.set(button, setTimeout(() => { button.textContent = label; }, 2000));
        } catch { button.textContent = label; input.focus(); input.select(); copyStatus.textContent = "링크를 선택했어요. 직접 복사해주세요."; }
        finally { button.disabled = false; }
    }));
    let summaryLoading = false;
    async function queueSummary() {
        if (summaryLoading) return;
        summaryLoading = true;
        const label = document.getElementById("drawingQueueNavSummary");
        try {
            const response = await fetch("/auth/dashboard/drawing/queue?offset=0&limit=1", {cache: "no-store"});
            const data = await response.json();
            if (!response.ok) throw new Error("대기열 조회 실패");
            label.textContent = `재생 중 ${data.playing_count} · 대기 ${data.queued_count}`;
        } catch { label.textContent = "대기열 확인 · 재생 취소"; }
        finally { summaryLoading = false; }
    }
    window.addEventListener("drawing-settings-saved", queueSummary);
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") queueSummary(); });
    setInterval(() => { if (document.visibilityState === "visible") queueSummary(); }, 3000);
    queueSummary();
})();
