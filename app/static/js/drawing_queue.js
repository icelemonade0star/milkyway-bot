(() => {
    "use strict";
    const root = "/auth/dashboard/drawing/queue", pageSize = 20;
    const list = document.getElementById("drawingQueueList"), status = document.getElementById("drawingQueueStatus");
    const summary = document.getElementById("drawingQueueSummary"), empty = document.getElementById("drawingQueueEmpty");
    const refresh = document.getElementById("refreshDrawingQueue");
    const previous = document.getElementById("previousDrawingQueue"), next = document.getElementById("nextDrawingQueue");
    const dialog = document.getElementById("cancelDrawingQueueDialog"), confirm = document.getElementById("confirmCancelDrawingQueue");
    let selected = null, cancellingNow = false, pointerIntent = false;
    function frozen() { return dialog.open || cancellingNow || pointerIntent; }
    function resume() { if (!frozen()) { reloadRequested = false; load(); } }
    const entries = new Map(), thumbnails = new Map(), tasks = [], cancelled = new Set();
    let offset = 0, total = 0, loading = false, reloadRequested = false, workers = 0, loaded = false, loadError = false, serverOffset = 0;
    const observer = new IntersectionObserver(items => {
        for (const item of items) if (item.isIntersecting) {
            observer.unobserve(item.target); tasks.push(item.target.loadPreview);
        }
        drain();
    }, {rootMargin: "200px"});
    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }
    async function request(path, method = "GET") {
        const response = await fetch(path, {method, cache: "no-store"});
        let data = null;
        try { data = await response.json(); } catch { /* JSON이 아닌 오류 응답도 화면에 안내한다. */ }
        if (!response.ok) throw new Error(typeof data?.error === "string" ? data.error :
            typeof data?.detail === "string" ? data.detail : "대기열 요청을 처리하지 못했어요. 다시 시도해주세요.");
        if (!data) throw new Error("대기열 응답을 확인하지 못했어요.");
        return data;
    }
    function drain() {
        while (workers < 2 && tasks.length) {
            workers++;
            tasks.shift()().finally(() => { workers--; drain(); });
        }
    }
    async function thumbnail(item) {
        if (!thumbnails.has(item.drawing_id)) thumbnails.set(item.drawing_id,
            request(`${root}/${encodeURIComponent(item.id)}/recording`).then(data => {
                const canvas = document.createElement("canvas"), recording = data.recording;
                canvas.width = recording.width; canvas.height = recording.height;
                DrawingCanvas.render(canvas, recording, Infinity, true);
                const small = document.createElement("canvas"), scale = Math.min(320 / canvas.width, 180 / canvas.height);
                small.width = Math.max(1, Math.round(canvas.width * scale));
                small.height = Math.max(1, Math.round(canvas.height * scale));
                small.getContext("2d").drawImage(canvas, 0, 0, small.width, small.height);
                return small.toDataURL("image/png");
            }));
        try { return await thumbnails.get(item.drawing_id); }
        catch (error) { thumbnails.delete(item.drawing_id); throw error; }
    }
    function updateEntry(entry, item, enabled) {
        entry.item = item;
        entry.enabled = enabled;
        const playing = item.status === "playing", manual = item.source === "hashtag";
        entry.node.classList.toggle("is-playing", playing && enabled);
        entry.position.textContent = `${item.position}번`;
        entry.state.textContent = !enabled ? (playing ? "재생 중단 상태" : "수신 꺼짐 · 대기 중") : playing ? "현재 재생 중" : "재생 대기 중";
        entry.source.textContent = manual ? "해시태그 수동 재생" : item.source === "replay" ? "후원 그림 다시 재생" : "후원";
        entry.donor.textContent = manual ? "스트리머 수동 재생" : item.nickname;
        entry.amount.textContent = manual ? "" : `${Number(item.amount).toLocaleString("ko-KR")}원`;
        entry.tag.textContent = item.hashtag;
        entry.image.alt = manual ? "수동 재생 그림" : `${item.nickname}님의 그림`;
        entry.button.disabled = entry.busy;
        entry.button.textContent = entry.busy ? "취소하고 있어요…" : playing && enabled ? "재생 중단" : "재생 취소";
        entry.button.setAttribute("aria-label", `${item.position}번 ${manual ? "수동 재생" : item.nickname + "님의 그림"} ${playing && enabled ? "재생 중단" : "재생 취소"}`);
        updateProgress(entry);
    }
    function updateProgress(entry) {
        const {item, enabled, progress, remaining} = entry;
        const duration = Number(item.duration_ms), start = Date.parse(item.started_at);
        const active = enabled && item.status === "playing" && duration > 0 && Number.isFinite(start);
        progress.hidden = remaining.hidden = !active;
        if (!active) return;
        const elapsed = Math.max(0, Date.now() + serverOffset - start);
        progress.value = Math.min(1, elapsed / duration);
        remaining.textContent = elapsed >= duration ? "표시 시간 종료 · OBS 상태 확인 중" : `남은 시간 ${Math.ceil((duration - elapsed) / 1000)}초`;
    }
    function addEntry(item) {
        const node = element("li", "drawing-queue-item"), picture = element("div", "drawing-history-picture");
        const image = element("img"), label = element("span", "", "그림 로딩 중…"), retry = element("button", "", "다시 보기");
        image.hidden = retry.hidden = true; retry.type = "button"; picture.append(image, label, retry);
        const details = element("div", "drawing-history-details"), heading = element("div", "drawing-queue-heading");
        const position = element("strong"), state = element("span"), source = element("span");
        heading.append(position, state, source);
        const donorRow = element("div", "drawing-history-donor"), donor = element("strong"), amount = element("span");
        donorRow.append(donor, amount);
        const tag = element("p", "drawing-queue-tag"), button = element("button", "cancel-drawing"); button.type = "button";
        const progress = element("progress", "drawing-queue-progress"), remaining = element("p", "drawing-queue-remaining");
        progress.max = 1; progress.setAttribute("aria-label", "재생 진행률"); progress.hidden = remaining.hidden = true;
        details.append(heading, donorRow, tag, progress, remaining, button); node.append(picture, details);
        const entry = {item, node, picture, image, position, state, source, donor, amount, tag, progress, remaining, button, busy: false};
        entries.set(item.id, entry);
        picture.loadPreview = async () => {
            if (!node.isConnected) return;
            retry.hidden = true; label.hidden = false; label.textContent = "그림 로딩 중…";
            try {
                const url = await thumbnail(item);
                if (!node.isConnected) return;
                image.src = url; image.hidden = false; label.hidden = true;
            } catch {
                if (node.isConnected) { label.textContent = "그림 로딩 실패"; retry.hidden = false; }
            }
        };
        retry.addEventListener("click", () => { retry.hidden = true; tasks.push(picture.loadPreview); drain(); });
        observer.observe(picture);
        button.addEventListener("click", () => {
            if (entry.busy || dialog.open) return;
            selected = entry;
            const target = entry.item, manual = target.source === "hashtag";
            const stopping = target.status === "playing" && entry.enabled;
            document.getElementById("cancelDrawingQueueHeading").textContent = stopping ?
                "재생을 중단할까요?" : "이 그림의 재생을 취소할까요?";
            confirm.textContent = stopping ? "재생 중단 확인" : "재생 취소 확인";
            document.getElementById("cancelDrawingQueueTarget").textContent = `${target.position}번 · ${manual ? "스트리머 수동 재생" : target.nickname + "님 · " + Number(target.amount).toLocaleString("ko-KR") + "원"}`;
            document.getElementById("cancelDrawingQueueTag").textContent = target.hashtag;
            document.getElementById("cancelDrawingQueueDescription").textContent = target.source === "donation" ?
                "실제 후원 항목을 삭제합니다. 재생 중이라면 방송을 중단하고 재생 이력에서도 삭제됩니다. 이 작업은 되돌릴 수 없어요." :
                "이 재생 항목을 대기열에서 삭제합니다. 이 작업은 되돌릴 수 없어요.";
            dialog.showModal(); controls();
        });
        return entry;
    }
    function controls() {
        refresh.disabled = previous.disabled = next.disabled = loading || frozen();
        previous.disabled ||= offset <= 0;
        next.disabled ||= offset + pageSize >= total;
        document.getElementById("drawingQueuePage").textContent = total ? `${Math.floor(offset / pageSize) + 1} / ${Math.ceil(total / pageSize)} 페이지` : "";
        empty.hidden = entries.size > 0 || !loaded;
        document.getElementById("drawingQueuePages").hidden = total <= pageSize;
    }
    async function load(announce = false) {
        if (frozen()) { reloadRequested = true; return; }
        if (loading) { reloadRequested = true; return; }
        for (const button of [refresh, previous, next]) button.classList.toggle("refresh-lock", loaded && !announce && !button.disabled);
        loading = true; controls();
        if (announce) status.textContent = "재생 대기열을 불러오고 있어요…";
        try {
            let data = await request(`${root}?offset=${offset}&limit=${pageSize}`);
            if (frozen()) { reloadRequested = true; return; }
            if (!Array.isArray(data.items)) throw new Error("대기열 목록을 확인하지 못했어요.");
            if (offset > 0 && offset >= data.total_count) {
                offset = Math.max(0, Math.floor((data.total_count - 1) / pageSize) * pageSize);
                data = await request(`${root}?offset=${offset}&limit=${pageSize}`);
                if (frozen()) { reloadRequested = true; return; }
                if (!Array.isArray(data.items)) throw new Error("대기열 목록을 확인하지 못했어요.");
            }
            total = data.total_count; loaded = true;
            const serverNow = Date.parse(data.server_now);
            serverOffset = Number.isFinite(serverNow) ? serverNow - Date.now() : 0;
            const incoming = new Set(data.items.map(item => item.id));
            for (const id of cancelled) if (!incoming.has(id)) cancelled.delete(id);
            for (const [id, entry] of entries) if (!incoming.has(id) || cancelled.has(id)) {
                observer.unobserve(entry.picture); entry.node.remove(); entries.delete(id);
            }
            let index = 0;
            for (const item of data.items) {
                if (cancelled.has(item.id)) continue;
                const entry = entries.get(item.id) || addEntry(item);
                updateEntry(entry, item, data.enabled);
                if (list.children[index] !== entry.node) list.insertBefore(entry.node, list.children[index] || null);
                index++;
            }
            const drawingIds = new Set(data.items.map(item => item.drawing_id));
            for (const id of thumbnails.keys()) if (!drawingIds.has(id)) thumbnails.delete(id);
            summary.textContent = `전체 ${data.total_count}개 · 재생 중 ${data.playing_count}개 · 대기 ${data.queued_count}개` +
                (data.enabled ? " · 3초마다 자동 갱신" : " · 그림 도네이션 받기가 꺼져 있어요. 대기열은 유지됩니다.");
            if (announce || loadError) status.textContent = "";
            loadError = false;
            window.dispatchEvent(new CustomEvent("drawing-receiving-state", {detail: {enabled: data.enabled}}));
        } catch (error) { loadError = true; status.textContent = error.message; }
        finally {
            for (const button of [refresh, previous, next]) button.classList.remove("refresh-lock");
            loading = false; controls();
            if (reloadRequested && !frozen()) { reloadRequested = false; load(); }
        }
    }
    list.addEventListener("pointerdown", event => {
        if (event.target.closest(".cancel-drawing")) pointerIntent = true;
    }, true);
    const releaseIntent = () => setTimeout(() => {
        if (!pointerIntent) return;
        pointerIntent = false;
        if (reloadRequested && !frozen()) resume();
    }, 0);
    window.addEventListener("pointerup", releaseIntent); window.addEventListener("pointercancel", releaseIntent);
    window.addEventListener("blur", () => {
        pointerIntent = false;
        if (reloadRequested && !frozen()) resume();
    });
    dialog.addEventListener("cancel", event => { if (cancellingNow) event.preventDefault(); });
    dialog.querySelector("form").addEventListener("submit", async event => {
        if (event.submitter?.value !== "confirm") return;
        event.preventDefault();
        if (!selected || cancellingNow) return;
        const entry = selected, id = entry.item.id;
        cancellingNow = entry.busy = true;
        dialog.querySelectorAll("button").forEach(button => { button.disabled = true; });
        const confirmLabel = confirm.textContent;
        confirm.textContent = confirmLabel === "재생 중단 확인" ? "중단하고 있어요…" : "취소하고 있어요…";
        try {
            const data = await request(`${root}/${encodeURIComponent(id)}`, "DELETE");
            cancelled.add(id); observer.unobserve(entry.picture); entry.node.remove(); entries.delete(id);
            status.textContent = data.was_playing ? "재생을 취소했어요. OBS의 다음 연결 확인 시 중단됩니다." : "대기열에서 그림을 제거했어요.";
            window.dispatchEvent(new Event("drawing-queue-changed"));
            window.dispatchEvent(new Event("drawing-queue-cancelled"));
        } catch (error) { status.textContent = error.message; }
        finally {
            cancellingNow = entry.busy = false;
            dialog.querySelectorAll("button").forEach(button => { button.disabled = false; });
            confirm.textContent = confirmLabel;
            if (entry.node.isConnected) updateEntry(entry, entry.item, entry.enabled);
            dialog.close();
        }
    });
    dialog.addEventListener("close", () => { selected = null; pointerIntent = false; controls(); resume(); });
    refresh.addEventListener("click", () => load(true));
    previous.addEventListener("click", () => { offset = Math.max(0, offset - pageSize); load(true); });
    next.addEventListener("click", () => { offset += pageSize; load(true); });
    window.addEventListener("drawing-queue-changed", () => load());
    window.addEventListener("drawing-settings-saved", () => load());
    window.addEventListener("pageshow", event => { if (event.persisted) load(); });
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });
    setInterval(() => { if (!loading && !frozen() && document.visibilityState === "visible") load(); }, 3000);
    setInterval(() => {
        if (!frozen() && document.visibilityState === "visible") for (const entry of entries.values()) updateProgress(entry);
    }, 1000);
    load(true);
})();
