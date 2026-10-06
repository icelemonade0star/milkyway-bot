(() => {
    "use strict";
    const form = document.getElementById("drawingSettings"), status = document.getElementById("settingsStatus");
    const preview = document.getElementById("drawingPreview");
    function options() {
        return Object.fromEntries(Array.from(form.elements).filter(item => item.name).map(item => [item.name,
            item.type === "checkbox" ? item.checked : Number(item.value)]));
    }
    function test() { preview.contentWindow.postMessage({type: "drawing-demo", options: options()}, location.origin); }
    document.getElementById("testDrawing").addEventListener("click", test);
    form.addEventListener("submit", async event => {
        event.preventDefault(); status.textContent = "설정을 저장하고 있어요…";
        const button = form.querySelector('[type="submit"]'); button.disabled = true;
        try {
            const response = await fetch("/auth/dashboard/drawing", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(options())});
            const data = await response.json();
            if (!response.ok) throw new Error(typeof data.error === "string" ? data.error :
                typeof data.detail === "string" ? data.detail : "설정 저장에 실패했습니다.");
            status.textContent = "설정을 저장했어요."; test();
        } catch (error) { status.textContent = error.message; }
        finally { button.disabled = false; }
    });
    document.querySelectorAll("[data-copy]").forEach(button => button.addEventListener("click", async () => {
        const input = document.getElementById(button.dataset.copy);
        try { await navigator.clipboard.writeText(input.value); status.textContent = "링크를 복사했어요."; }
        catch { input.focus(); input.select(); status.textContent = "링크를 선택했어요. 직접 복사해주세요."; }
    }));
})();
