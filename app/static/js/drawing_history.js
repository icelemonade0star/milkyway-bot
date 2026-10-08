(() => {
    "use strict";
    const root = "/auth/dashboard/drawing/history";
    const list = document.getElementById("drawingHistoryList");
    const status = document.getElementById("drawingHistoryStatus");
    const empty = document.getElementById("drawingHistoryEmpty");
    const refresh = document.getElementById("refreshDrawingHistory"), more = document.getElementById("moreDrawingHistory");
    const entries = new Map(), thumbnails = new Map(), previewTasks = [];
    let cursor = null, loading = false, replaying = 0, previewWorkers = 0, serverOffset = 0, expanded = false;
    let receiving = false, loaded = false;
    const observer = new IntersectionObserver(items => {
        for (const item of items) if (item.isIntersecting) {
            observer.unobserve(item.target);
            previewTasks.push(item.target.loadPreview);
        }
        drainPreviews();
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
        try { data = await response.json(); } catch { /* 오류 본문이 JSON이 아니어도 상태를 안내한다. */ }
        if (!response.ok) {
            const error = new Error(typeof data?.error === "string" ? data.error :
                typeof data?.detail === "string" ? data.detail : "요청을 처리하지 못했어요. 다시 시도해주세요.");
            error.status = response.status; throw error;
        }
        if (!data) throw new Error("응답을 확인하지 못했어요. 다시 시도해주세요.");
        return data;
    }
    function updateEntry(entry) {
        const pending = entry.item.replay_status;
        entry.button.disabled = entry.busy || !receiving || entry.item.status !== "done" || Boolean(pending);
        entry.button.textContent = entry.busy ? "대기열에 추가하고 있어요…" :
            pending === "queued" ? "다시 재생 대기 중" : pending === "playing" ? "다시 재생 중" : "방송에서 다시 재생";
        entry.state.textContent = entry.item.status === "playing" ? "후원 그림 재생 중" :
            !receiving ? "그림 도네이션 받기를 켜면 다시 재생할 수 있어요." : "후원 그림 재생 완료";
    }
    function expireEntries() {
        const now = Date.now() + serverOffset;
        for (const [id, entry] of entries) if (Date.parse(entry.item.expires_at) <= now) {
            observer.unobserve(entry.picture); entry.node.remove(); entries.delete(id);
        }
        empty.hidden = entries.size > 0 || loading || !loaded;
        const drawingIds = new Set(Array.from(entries.values(), entry => entry.item.drawing_id));
        for (const id of thumbnails.keys()) if (!drawingIds.has(id)) thumbnails.delete(id);
    }
    async function thumbnail(item) {
        if (!thumbnails.has(item.drawing_id)) {
            const promise = request(`${root}/${encodeURIComponent(item.id)}/recording`).then(data => {
                const source = document.createElement("canvas"), recording = data.recording;
                source.width = recording.width; source.height = recording.height;
                DrawingCanvas.render(source, recording, Infinity, true);
                const output = document.createElement("canvas");
                const scale = Math.min(320 / source.width, 180 / source.height);
                output.width = Math.max(1, Math.round(source.width * scale));
                output.height = Math.max(1, Math.round(source.height * scale));
                output.getContext("2d").drawImage(source, 0, 0, output.width, output.height);
                return output.toDataURL("image/png");
            });
            thumbnails.set(item.drawing_id, promise);
        }
        try { return await thumbnails.get(item.drawing_id); }
        catch (error) { thumbnails.delete(item.drawing_id); throw error; }
    }
    function drainPreviews() {
        while (previewWorkers < 2 && previewTasks.length) {
            const task = previewTasks.shift(); previewWorkers++;
            task().finally(() => { previewWorkers--; drainPreviews(); });
        }
    }
    function addEntry(item) {
        if (entries.has(item.id)) return;
        const node = element("li", "drawing-history-item"), picture = element("div", "drawing-history-picture");
        const image = element("img"), label = element("span", "", "미리보기를 불러오고 있어요…");
        const retry = element("button", "", "미리보기 다시 불러오기");
        retry.type = "button"; retry.hidden = true; image.hidden = true; image.alt = `${item.nickname}님의 후원 그림`;
        picture.append(image, label, retry);
        const details = element("div", "drawing-history-details"), donor = element("div", "drawing-history-donor");
        donor.append(element("strong", "", item.nickname), element("span", "", `${Number(item.amount).toLocaleString("ko-KR")}원`));
        const time = element("p", "drawing-history-time");
        const played = element("time", "", new Date(item.played_at).toLocaleString("ko-KR"));
        played.dateTime = item.played_at; time.append("재생 · ", played);
        const state = element("span", "drawing-history-state"), button = element("button"); button.type = "button";
        button.setAttribute("aria-label", `${item.nickname}님의 후원 그림 방송에서 다시 재생`);
        details.append(donor, time, state, button); node.append(picture, details); list.append(node);
        const entry = {item, node, picture, button, state, busy: false}; entries.set(item.id, entry); updateEntry(entry);
        picture.loadPreview = async () => {
            if (!node.isConnected) return;
            retry.hidden = true; label.hidden = false; label.textContent = "미리보기를 불러오고 있어요…";
            try {
                const url = await thumbnail(item);
                if (!node.isConnected) return;
                image.src = url; image.hidden = false; label.hidden = true;
            } catch (error) {
                if (error.status === 410 || error.status === 404) {
                    node.remove(); entries.delete(item.id); expireEntries();
                } else {
                    label.textContent = "미리보기를 불러오지 못했어요."; retry.hidden = false;
                }
            }
        };
        retry.addEventListener("click", () => { retry.hidden = true; previewTasks.push(picture.loadPreview); drainPreviews(); });
        observer.observe(picture);
        button.addEventListener("click", async () => {
            if (button.disabled) return;
            expireEntries(); if (!node.isConnected) return;
            entry.busy = true; replaying++; updateEntry(entry);
            try {
                const data = await request(`${root}/${encodeURIComponent(item.id)}/replay`, "POST");
                item.replay_status = data.status;
                status.textContent = data.already_queued ? "이미 다시 재생 대기 중이거나 재생 중인 그림이에요." :
                    "방송 대기열에 추가했어요. OBS 연결 시 순서대로 다시 재생됩니다.";
            } catch (error) {
                status.textContent = error.message;
                if (error.status === 410 || error.status === 404) { node.remove(); entries.delete(item.id); }
            } finally { entry.busy = false; replaying--; updateEntry(entry); expireEntries(); }
        });
    }
    async function load(reset = true, announce = true) {
        if (loading) return;
        loading = true; refresh.disabled = more.disabled = true;
        if (announce) status.textContent = "후원 그림 이력을 불러오고 있어요…";
        try {
            const data = await request(root + (!reset && cursor ? `?before=${encodeURIComponent(cursor)}` : ""));
            if (!Array.isArray(data.items)) throw new Error("후원 그림 이력을 확인하지 못했어요.");
            serverOffset = Date.parse(data.server_now) - Date.now(); receiving = Boolean(data.enabled); loaded = true;
            if (reset) { observer.disconnect(); previewTasks.length = 0; list.replaceChildren(); entries.clear(); expanded = false; }
            else expanded = true;
            for (const item of data.items) addEntry(item);
            cursor = data.next_cursor; more.hidden = !cursor;
            if (announce) status.textContent = "";
        } catch (error) { status.textContent = error.message; }
        finally { loading = false; refresh.disabled = more.disabled = false; expireEntries(); }
    }
    refresh.addEventListener("click", () => load());
    more.addEventListener("click", () => load(false));
    window.addEventListener("drawing-settings-saved", event => {
        receiving = Boolean(event.detail.enabled);
        for (const entry of entries.values()) updateEntry(entry);
    });
    window.addEventListener("pageshow", event => { if (event.persisted) load(); });
    setInterval(expireEntries, 1000);
    setInterval(() => { if (!expanded && !loading && !replaying && document.visibilityState === "visible") load(true, false); }, 30000);
    load();
})();
