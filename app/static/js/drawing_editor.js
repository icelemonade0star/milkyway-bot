(() => {
    "use strict";
    const config = JSON.parse(document.getElementById("drawingConfig").textContent);
    const canvas = document.getElementById("drawingCanvas"), ctx = canvas.getContext("2d");
    const status = document.getElementById("drawingStatus"), save = document.getElementById("saveDrawing");
    const result = document.getElementById("drawingResult");
    const canvasStage = document.getElementById("drawingCanvasStage");
    const backgroundColor = document.getElementById("canvasBackgroundColor");
    function updateBackgroundColor() {
        canvasStage.style.setProperty("--drawing-background", backgroundColor.value);
        document.querySelectorAll("[data-background-color]").forEach(item =>
            item.setAttribute("aria-pressed", String(item.dataset.backgroundColor === backgroundColor.value)));
    }
    document.querySelectorAll("[data-background-color]").forEach(button => button.addEventListener("click", () => {
        backgroundColor.value = button.dataset.backgroundColor;
        updateBackgroundColor();
    }));
    backgroundColor.addEventListener("input", updateBackgroundColor);
    updateBackgroundColor();
    const liveImage = document.getElementById("liveBackgroundImage");
    const backgroundMode = document.getElementById("canvasBackgroundMode");
    const transparency = document.getElementById("liveBackgroundTransparency");
    const refreshBackground = document.getElementById("refreshLiveBackground");
    const backgroundStatus = document.getElementById("liveBackgroundStatus");
    let backgroundLoading = false, backgroundRetryAt = 0, backgroundRetryTimer = 0;
    function updateBackgroundRefreshState() {
        clearTimeout(backgroundRetryTimer);
        const remaining = backgroundRetryAt - Date.now();
        refreshBackground.disabled = backgroundLoading || remaining > 0;
        if (remaining > 0) backgroundRetryTimer = setTimeout(updateBackgroundRefreshState, remaining + 20);
    }
    function startBackgroundCooldown(seconds) {
        backgroundRetryAt = Date.now() + seconds * 1000;
        updateBackgroundRefreshState();
    }
    function finishBackgroundLoading() {
        backgroundLoading = false;
        updateBackgroundRefreshState();
    }
    function updateBackgroundTransparency() {
        canvasStage.style.setProperty("--live-background-opacity", String(1 - Number(transparency.value) / 100));
        document.getElementById("liveBackgroundTransparencyValue").value = `${transparency.value}%`;
    }
    transparency.addEventListener("input", updateBackgroundTransparency);
    updateBackgroundTransparency();
    liveImage.addEventListener("load", () => {
        liveImage.hidden = backgroundMode.value !== "live"; backgroundStatus.textContent = "";
        finishBackgroundLoading();
    });
    liveImage.addEventListener("error", () => {
        liveImage.hidden = true;
        backgroundStatus.textContent = "방송 이미지를 불러오지 못했어요. 계속 그림을 그릴 수 있어요.";
        finishBackgroundLoading();
    });
    async function loadLiveBackground() {
        if (backgroundLoading || backgroundMode.value !== "live") return;
        if (Date.now() < backgroundRetryAt) {
            backgroundStatus.textContent = `${Math.ceil((backgroundRetryAt - Date.now()) / 1000)}초 후 다시 시도해주세요.`;
            return;
        }
        backgroundLoading = true;
        refreshBackground.disabled = true;
        backgroundStatus.textContent = "방송 이미지를 불러오고 있어요…";
        try {
            const response = await fetch(config.background_path, {cache: "no-store"});
            const retry = Number(response.headers.get("Retry-After"));
            const retrySeconds = !response.ok && Number.isFinite(retry) && retry > 0 ? Math.min(300, Math.ceil(retry)) : 0;
            if (response.ok) startBackgroundCooldown(5);
            else if (retrySeconds) startBackgroundCooldown(retrySeconds);
            let data = null;
            try { data = await response.json(); }
            catch { if (response.ok) throw new Error("방송 이미지 응답 형식 오류"); }
            if (!response.ok) {
                const message = typeof data?.error === "string" ? data.error :
                    typeof data?.detail === "string" ? data.detail : "방송 이미지 조회에 실패했어요.";
                backgroundStatus.textContent = message + (retrySeconds ? ` ${retrySeconds}초 후 다시 시도해주세요.` : "");
                finishBackgroundLoading(); return;
            }
            if (typeof data?.image_url !== "string" || !data.image_url) {
                liveImage.hidden = true; liveImage.removeAttribute("src");
                backgroundStatus.textContent = "현재 사용할 수 있는 방송 이미지가 없어요.";
                finishBackgroundLoading(); return;
            }
            // 외부 이미지는 캔버스 아래에서만 표시하여 PNG와 재생 기록에 섞이지 않게 한다.
            const imageUrl = new URL(data.image_url);
            imageUrl.searchParams.set("_mw", String(Date.now()));
            liveImage.src = imageUrl.href;
        } catch {
            liveImage.hidden = true;
            backgroundStatus.textContent = "방송 이미지를 불러오지 못했어요. 계속 그림을 그릴 수 있어요.";
            finishBackgroundLoading();
        }
    }
    refreshBackground.addEventListener("click", loadLiveBackground);
    function updateBackgroundMode() {
        const live = backgroundMode.value === "live";
        canvasStage.dataset.backgroundMode = backgroundMode.value;
        document.getElementById("liveBackgroundControls").hidden = !live;
        document.getElementById("backgroundColorControl").hidden = backgroundMode.value !== "color";
        liveImage.hidden = !live || !liveImage.complete || !liveImage.naturalWidth;
        if (live && !liveImage.getAttribute("src")) loadLiveBackground();
    }
    backgroundMode.addEventListener("change", updateBackgroundMode);
    updateBackgroundMode();
    window.addEventListener("pageshow", () => {
        updateBackgroundColor(); updateBackgroundTransparency(); updateBackgroundMode();
        updateBackgroundRefreshState();
    });
    const recording = {width: canvas.width, height: canvas.height, actions: []};
    let tool = "pen", current = null, pointer = null, started = null, pointCount = 0;
    const undoStack = [];
    let saveKey = crypto.randomUUID(), saving = false;
    DrawingCanvas.render(canvas, recording, Infinity, true);
    function timestamp() { return Math.min(600000, Math.round(performance.now() - started)); }
    function changed() { saveKey = crypto.randomUUID(); result.hidden = true; status.textContent = ""; }
    function point(event) {
        const rect = canvas.getBoundingClientRect();
        return {x: Math.max(0, Math.min(canvas.width, (event.clientX - rect.left) * canvas.width / rect.width)),
            y: Math.max(0, Math.min(canvas.height, (event.clientY - rect.top) * canvas.height / rect.height)), t: timestamp()};
    }
    function canRecord() {
        if (saving) return false;
        if (pointCount >= 25000 || recording.actions.length >= 2000 || (started !== null && performance.now() - started >= 600000)) {
            status.textContent = "기록 한도에 도달했어요. 지금 그림을 저장해주세요."; return false;
        }
        return true;
    }
    canvas.addEventListener("pointerdown", event => {
        if (pointer !== null || (event.pointerType === "mouse" && event.button !== 0) || !canRecord()) return;
        if (started === null) started = performance.now();
        changed();
        const first = point(event), color = document.getElementById("penColor").value;
        if (tool === "fill") {
            const action = {type: "stroke", tool, color, width: 1, points: [first]};
            recording.actions.push(action); undoStack.push({type: "stroke", action});
            pointCount++; DrawingCanvas.fill(ctx, first.x, first.y, color); return;
        }
        pointer = event.pointerId; canvas.setPointerCapture(pointer);
        current = {type: "stroke", tool, color,
            width: Number(document.getElementById("penWidth").value), points: [first]};
        recording.actions.push(current); pointCount++;
        undoStack.push({type: "stroke", action: current});
        DrawingCanvas.stroke(ctx, current, true);
    });
    canvas.addEventListener("pointermove", event => {
        if (event.pointerId !== pointer || !current || !canRecord()) return;
        const next = point(event), previous = current.points.at(-1);
        if (next.t - previous.t < 12 && Math.hypot(next.x - previous.x, next.y - previous.y) < 3) return;
        current.points.push(next); pointCount++;
        DrawingCanvas.stroke(ctx, {...current, points: [previous, next]}, true);
    });
    function end(event) {
        if (event.pointerId !== pointer) return;
        if (canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
        current = null; pointer = null;
    }
    canvas.addEventListener("pointerup", end); canvas.addEventListener("pointercancel", end);
    function setTool(nextTool) {
        tool = nextTool;
        document.querySelectorAll("[data-tool]").forEach(item => item.setAttribute("aria-pressed", String(item.dataset.tool === tool)));
    }
    document.querySelectorAll("[data-tool]").forEach(button => button.addEventListener("click", () => setTool(button.dataset.tool)));
    document.querySelectorAll("[data-color]").forEach(button => button.addEventListener("click", () => {
        document.getElementById("penColor").value = button.dataset.color;
        document.querySelectorAll("[data-color]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
        setTool("pen");
    }));
    document.getElementById("penColor").addEventListener("input", () => {
        document.querySelectorAll("[data-color]").forEach(item => item.setAttribute("aria-pressed", String(item.dataset.color === document.getElementById("penColor").value)));
        setTool("pen");
    });
    document.getElementById("penWidth").addEventListener("input", event => { document.getElementById("widthValue").value = event.target.value; });
    function refreshPointCount() {
        pointCount = recording.actions.reduce((count, action) => count + action.points.length, 0);
    }
    function edit(type) {
        if (saving || current) return;
        if (type === "undo") {
            const operation = undoStack.pop();
            if (!operation) return;
            if (operation.type === "stroke" && recording.actions.at(-1) === operation.action) recording.actions.pop();
            else if (operation.type === "clear") {
                recording.actions.push(...operation.actions); started = operation.started;
            }
            else return;
        } else if (type === "clear") {
            if (!recording.actions.length && started === null) return;
            // 지우기 이전 기록과 시간은 로컬 되돌리기에만 보관하고, 새 기록은 다시 0부터 시작한다.
            undoStack.push({type: "clear", actions: recording.actions.slice(), started});
            recording.actions.length = 0; started = null;
        } else return;
        refreshPointCount(); changed(); DrawingCanvas.render(canvas, recording, Infinity, true);
    }
    document.getElementById("undoDrawing").addEventListener("click", () => edit("undo"));
    document.getElementById("clearDrawing").addEventListener("click", () => edit("clear"));
    window.addEventListener("keydown", event => {
        const target = event.target;
        if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.key.toLowerCase() !== "z" || event.isComposing ||
            (target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
        event.preventDefault(); edit("undo");
    });
    save.addEventListener("click", async () => {
        if (current || saving) return;
        if (!recording.actions.length) { status.textContent = "먼저 그림을 그려주세요."; return; }
        saving = true; save.disabled = true; status.textContent = "그림을 저장하고 있어요…";
        const finalPng = canvas.toDataURL("image/png");
        try {
            const response = await fetch(config.save_path, {method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({save_key: saveKey, recording, final_png: finalPng})});
            const data = await response.json();
            if (!response.ok) throw new Error(typeof data.error === "string" ? data.error :
                typeof data.detail === "string" ? data.detail : "그림 저장에 실패했습니다.");
            document.getElementById("drawingTag").value = data.hashtag;
            document.getElementById("savedDrawingPreview").src = finalPng;
            result.hidden = false; status.textContent = "저장 완료! 아래 해시태그를 후원 메시지에 넣어주세요.";
            result.scrollIntoView({behavior: "smooth", block: "nearest"});
        } catch (error) { status.textContent = error.message; }
        finally { saving = false; save.disabled = false; }
    });
    document.getElementById("copyDrawingTag").addEventListener("click", async () => {
        const input = document.getElementById("drawingTag");
        try { await navigator.clipboard.writeText(input.value); status.textContent = "해시태그를 복사했어요."; }
        catch { input.focus(); input.select(); status.textContent = "해시태그를 선택했어요. 직접 복사해주세요."; }
    });
})();
