(() => {
    "use strict";
    const config = JSON.parse(document.getElementById("drawingConfig").textContent);
    const canvas = document.getElementById("drawingCanvas"), ctx = canvas.getContext("2d");
    const status = document.getElementById("drawingStatus"), save = document.getElementById("saveDrawing");
    const result = document.getElementById("drawingResult");
    const recording = {width: canvas.width, height: canvas.height, actions: []};
    let tool = "pen", current = null, pointer = null, started = null, pointCount = 0;
    let saveKey = crypto.randomUUID(), saving = false;
    DrawingCanvas.render(canvas, recording);
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
        changed(); pointer = event.pointerId; canvas.setPointerCapture(pointer);
        current = {type: "stroke", tool, color: document.getElementById("penColor").value,
            width: Number(document.getElementById("penWidth").value), points: [point(event)]};
        recording.actions.push(current); pointCount++;
        DrawingCanvas.stroke(ctx, current);
    });
    canvas.addEventListener("pointermove", event => {
        if (event.pointerId !== pointer || !current || !canRecord()) return;
        const next = point(event), previous = current.points.at(-1);
        if (next.t - previous.t < 12 && Math.hypot(next.x - previous.x, next.y - previous.y) < 3) return;
        current.points.push(next); pointCount++;
        DrawingCanvas.stroke(ctx, {...current, points: [previous, next]});
    });
    function end(event) {
        if (event.pointerId !== pointer) return;
        if (canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer);
        current = null; pointer = null;
    }
    canvas.addEventListener("pointerup", end); canvas.addEventListener("pointercancel", end);
    document.querySelectorAll("[data-tool]").forEach(button => button.addEventListener("click", () => {
        tool = button.dataset.tool;
        document.querySelectorAll("[data-tool]").forEach(item => item.setAttribute("aria-pressed", String(item === button)));
    }));
    document.getElementById("penWidth").addEventListener("input", event => { document.getElementById("widthValue").value = event.target.value; });
    function edit(type) {
        if (started === null || current || !canRecord() || !DrawingCanvas.visibleStrokes(recording).length) return;
        recording.actions.push({type, t: timestamp()}); pointCount++; changed(); DrawingCanvas.render(canvas, recording);
    }
    document.getElementById("undoDrawing").addEventListener("click", () => edit("undo"));
    document.getElementById("clearDrawing").addEventListener("click", () => edit("clear"));
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
