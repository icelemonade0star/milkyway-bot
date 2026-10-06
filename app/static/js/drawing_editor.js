(() => {
    "use strict";
    const config = JSON.parse(document.getElementById("drawingConfig").textContent);
    const canvas = document.getElementById("drawingCanvas"), ctx = canvas.getContext("2d");
    const status = document.getElementById("drawingStatus"), save = document.getElementById("saveDrawing");
    const result = document.getElementById("drawingResult");
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
        if (saving || started === null || current) return;
        if (type === "undo") {
            const operation = undoStack.pop();
            if (!operation) return;
            if (operation.type === "stroke" && recording.actions.at(-1) === operation.action) recording.actions.pop();
            else if (operation.type === "clear") recording.actions.push(...operation.actions);
            else return;
        } else if (type === "clear") {
            if (!recording.actions.length) return;
            const actions = recording.actions.slice();
            recording.actions.length = 0; undoStack.push({type: "clear", actions});
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
