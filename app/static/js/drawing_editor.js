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
        backgroundColor.parentElement.classList.toggle("is-selected",
            !Array.from(document.querySelectorAll("[data-background-color]")).some(item => item.dataset.backgroundColor === backgroundColor.value));
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
        document.querySelectorAll("button[data-background-mode]").forEach(item =>
            item.setAttribute("aria-pressed", String(item.dataset.backgroundMode === backgroundMode.value)));
        liveImage.hidden = !live || !liveImage.complete || !liveImage.naturalWidth;
        if (live && !liveImage.getAttribute("src")) loadLiveBackground();
    }
    backgroundMode.addEventListener("change", updateBackgroundMode);
    document.querySelectorAll("button[data-background-mode]").forEach(button => button.addEventListener("click", () => {
        backgroundMode.value = button.dataset.backgroundMode; updateBackgroundMode();
    }));
    updateBackgroundMode();
    window.addEventListener("pageshow", () => {
        updateBackgroundColor(); updateBackgroundTransparency(); updateBackgroundMode();
        updateBackgroundRefreshState();
    });
    const recording = {width: canvas.width, height: canvas.height, actions: []};
    const undo = document.getElementById("undoDrawing"), redo = document.getElementById("redoDrawing");
    const clear = document.getElementById("clearDrawing"), clearDialog = document.getElementById("clearDrawingDialog");
    const saveControls = document.getElementById("drawingSaveControls");
    const copyLabel = document.getElementById("copyDrawingLabel");
    const undoStack = [], redoStack = [];
    let tool = "pen", current = null, pointer = null, strokeStarted = 0, pointCount = 0;
    let saveKey = crypto.randomUUID(), saving = false, finished = false, copied = false;
    DrawingCanvas.render(canvas, recording, Infinity, true);
    function recordedDuration() { return recording.actions.at(-1)?.points.at(-1).t ?? 0; }
    function timestamp() {
        // 획 사이의 대기 시간은 제외하고, 현재 남아 있는 기록 뒤에 새 획을 이어 붙인다.
        return current ? Math.min(600000, current.points[0].t + Math.round(Math.max(0, performance.now() - strokeStarted))) : recordedDuration();
    }
    function reachedLimit() {
        return pointCount >= 25000 || recording.actions.length >= 2000 || recordedDuration() >= 600000;
    }
    function paintLocked() { return saving || finished || clearDialog.open; }
    function updateSteps() {
        const phase = finished ? (copied ? 3 : 2) : saving ? 1 : 0;
        document.querySelectorAll("[data-step]").forEach(item => {
            const step = Number(item.dataset.step);
            item.classList.toggle("is-complete", step < phase);
            item.classList.toggle("is-current", step === phase);
            if (step === phase) item.setAttribute("aria-current", "step");
            else item.removeAttribute("aria-current");
            item.querySelector(".step-number").textContent = step < phase ? "✓" : String(step + 1);
        });
    }
    function updateBrushPreview() {
        const width = Number(document.getElementById("penWidth").value);
        const color = document.getElementById("penColor").value;
        const dot = document.getElementById("brushPreviewDot");
        dot.style.width = dot.style.height = `${Math.min(36, Math.max(2, width))}px`;
        dot.style.backgroundColor = tool === "eraser" ? "#ffffff" : color;
        dot.style.border = tool === "eraser" || color === "#ffffff" ? "1px solid #8a958f" : "0";
        document.getElementById("brushPreview").title = `굵기 ${width}px`;
        document.getElementById("widthValue").value = width;
        document.querySelectorAll("[data-color]").forEach(item =>
            item.setAttribute("aria-pressed", String(tool !== "eraser" && item.dataset.color === color)));
        document.getElementById("penColor").parentElement.classList.toggle("is-selected",
            tool !== "eraser" && !Array.from(document.querySelectorAll("[data-color]")).some(item => item.dataset.color === color));
    }
    function updateEditor() {
        const locked = paintLocked(), busy = locked || current !== null;
        save.disabled = busy || !recording.actions.length;
        save.textContent = saving ? "그림을 저장하고 있어요…" : "그림 저장하기";
        undo.disabled = busy || !undoStack.length;
        redo.disabled = busy || !redoStack.length;
        clear.disabled = busy || !recording.actions.length;
        document.querySelectorAll("[data-tool], [data-color], #penColor, #penWidth").forEach(item => { item.disabled = busy; });
        canvas.setAttribute("aria-disabled", String(locked || reachedLimit()));
        result.hidden = !finished;
        saveControls.hidden = finished;
        document.getElementById("emptyDrawingHint").hidden = recording.actions.length > 0 || finished;
        if (reachedLimit() && !saving && !finished && !status.textContent)
            status.textContent = "기록 한도에 도달했어요. 지금 그림을 저장해주세요.";
        copyLabel.textContent = copied ? "복사했어요" : "해시태그 복사";
        updateSteps();
    }
    function changed() {
        saveKey = crypto.randomUUID(); finished = false; copied = false; status.textContent = "";
    }
    function point(event) {
        const rect = canvas.getBoundingClientRect();
        return {x: Math.max(0, Math.min(canvas.width, (event.clientX - rect.left) * canvas.width / rect.width)),
            y: Math.max(0, Math.min(canvas.height, (event.clientY - rect.top) * canvas.height / rect.height)), t: timestamp()};
    }
    function canRecord() {
        if (paintLocked()) return false;
        if (reachedLimit()) {
            status.textContent = "기록 한도에 도달했어요. 지금 그림을 저장해주세요.";
            updateEditor(); return false;
        }
        return true;
    }
    canvas.addEventListener("pointerdown", event => {
        if (pointer !== null || (event.pointerType === "mouse" && event.button !== 0) || !canRecord()) return;
        strokeStarted = performance.now();
        changed(); redoStack.length = 0;
        const first = point(event), color = document.getElementById("penColor").value;
        if (tool === "fill") {
            const action = {type: "stroke", tool, color, width: 1, points: [first]};
            recording.actions.push(action); undoStack.push({type: "stroke", action});
            pointCount++; DrawingCanvas.fill(ctx, first.x, first.y, color); updateEditor(); return;
        }
        pointer = event.pointerId; canvas.setPointerCapture(pointer);
        current = {type: "stroke", tool, color, width: Number(document.getElementById("penWidth").value), points: [first]};
        recording.actions.push(current); pointCount++;
        undoStack.push({type: "stroke", action: current});
        DrawingCanvas.stroke(ctx, current, true); updateEditor();
    });
    canvas.addEventListener("pointermove", event => {
        if (event.pointerId !== pointer || !current || !canRecord()) return;
        const next = point(event), previous = current.points.at(-1);
        if (next.t - previous.t < 12 && Math.hypot(next.x - previous.x, next.y - previous.y) < 3) return;
        current.points.push(next); pointCount++;
        DrawingCanvas.stroke(ctx, {...current, points: [previous, next]}, true);
        if (reachedLimit()) updateEditor();
    });
    function end(event) {
        if (event.pointerId !== pointer) return;
        if (canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
        current = null; pointer = null; updateEditor();
    }
    canvas.addEventListener("pointerup", end); canvas.addEventListener("pointercancel", end);
    function setTool(nextTool) {
        tool = nextTool;
        document.querySelectorAll("[data-tool]").forEach(item => item.setAttribute("aria-pressed", String(item.dataset.tool === tool)));
        updateBrushPreview();
    }
    document.querySelectorAll("[data-tool]").forEach(button => button.addEventListener("click", () => setTool(button.dataset.tool)));
    document.querySelectorAll("[data-color]").forEach(button => button.addEventListener("click", () => {
        document.getElementById("penColor").value = button.dataset.color;
        if (tool === "eraser") setTool("pen"); else updateBrushPreview();
    }));
    document.getElementById("penColor").addEventListener("input", () => {
        if (tool === "eraser") setTool("pen"); else updateBrushPreview();
    });
    document.getElementById("penWidth").addEventListener("input", updateBrushPreview);
    function refreshPointCount() {
        pointCount = recording.actions.reduce((count, action) => count + action.points.length, 0);
    }
    function edit(type) {
        if (paintLocked() || current) return;
        if (type === "undo") {
            const operation = undoStack.at(-1);
            if (!operation) return;
            if (operation.type === "stroke" && recording.actions.at(-1) === operation.action) recording.actions.pop();
            else if (operation.type === "clear") {
                recording.actions.push(...operation.actions);
            } else {
                undoStack.pop(); updateEditor(); return;
            }
            undoStack.pop(); redoStack.push(operation);
        } else if (type === "redo") {
            const operation = redoStack.pop();
            if (!operation) return;
            if (operation.type === "stroke") {
                recording.actions.push(operation.action);
            } else if (operation.type === "clear") {
                recording.actions.length = 0;
            }
            undoStack.push(operation);
        } else if (type === "clear") {
            if (!recording.actions.length) return;
            // 지우기 전 기록은 편집 이력에만 보관한다. 새 기록은 0부터 시작한다.
            undoStack.push({type: "clear", actions: recording.actions.slice()});
            redoStack.length = 0; recording.actions.length = 0;
        } else return;
        refreshPointCount(); changed(); DrawingCanvas.render(canvas, recording, Infinity, true); updateEditor();
    }
    undo.addEventListener("click", () => edit("undo"));
    redo.addEventListener("click", () => edit("redo"));
    clear.addEventListener("click", () => {
        if (paintLocked() || current || !recording.actions.length) return;
        clearDialog.returnValue = ""; clearDialog.showModal(); updateEditor();
    });
    clearDialog.querySelector("form").addEventListener("submit", event => {
        if (event.submitter?.value !== "clear") return;
        event.preventDefault(); clearDialog.close("clear"); edit("clear");
    });
    clearDialog.addEventListener("close", updateEditor);
    window.addEventListener("keydown", event => {
        const target = event.target, key = event.key.toLowerCase();
        if (!(event.ctrlKey || event.metaKey) || event.isComposing || paintLocked() || current ||
            (target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
        if (key === "z" || key === "y") {
            event.preventDefault(); edit(key === "y" || event.shiftKey ? "redo" : "undo");
        }
    });
    save.addEventListener("click", async () => {
        if (current || paintLocked()) return;
        if (!recording.actions.length) { status.textContent = "먼저 그림을 그려주세요."; return; }
        saving = true; status.textContent = "그림을 저장하고 있어요…"; updateEditor();
        try {
            const finalPng = canvas.toDataURL("image/png");
            const response = await fetch(config.save_path, {method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({save_key: saveKey, recording, final_png: finalPng})});
            const data = await response.json();
            if (!response.ok) throw new Error(typeof data?.error === "string" ? data.error :
                typeof data?.detail === "string" ? data.detail : "그림 저장에 실패했습니다.");
            if (typeof data?.hashtag !== "string" || !data.hashtag) throw new Error("그림 해시태그를 받지 못했어요. 다시 저장해주세요.");
            document.getElementById("drawingTag").value = data.hashtag;
            finished = true; copied = false; status.textContent = "";
            updateEditor(); result.scrollIntoView({behavior: "smooth", block: "nearest"});
        } catch (error) { status.textContent = error instanceof Error ? error.message : "그림 저장에 실패했습니다."; }
        finally { saving = false; updateEditor(); }
    });
    document.getElementById("editSavedDrawing").addEventListener("click", () => {
        finished = false; copied = false; status.textContent = ""; updateEditor();
        canvas.focus({preventScroll: true});
    });
    document.getElementById("copyDrawingTag").addEventListener("click", async () => {
        const input = document.getElementById("drawingTag"), button = document.getElementById("copyDrawingTag");
        button.disabled = true;
        try {
            await navigator.clipboard.writeText(input.value);
            copied = true; status.textContent = "해시태그를 복사했어요. 치지직 후원 메시지에 붙여넣어주세요.";
        } catch {
            input.focus(); input.select(); status.textContent = "해시태그를 선택했어요. 직접 복사해주세요.";
        } finally { button.disabled = false; updateEditor(); }
    });
    updateBrushPreview(); updateEditor();
})();
