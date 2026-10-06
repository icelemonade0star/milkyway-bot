(() => {
    "use strict";
    const config = JSON.parse(document.getElementById("replayConfig").textContent);
    const overlay = document.getElementById("drawingOverlay"), donor = document.getElementById("drawingDonor");
    const canvas = document.getElementById("replayCanvas");
    let active = null, anchor = 0, animation = 0, finalShown = false, busy = false;
    function fitCanvas() {
        if (!active) return;
        const donorHeight = donor.hidden ? 0 : donor.getBoundingClientRect().height;
        const availableHeight = Math.max(0, window.innerHeight - donorHeight);
        const scale = Math.min(window.innerWidth / canvas.width, availableHeight / canvas.height);
        canvas.style.width = `${canvas.width * scale}px`;
        canvas.style.height = `${canvas.height * scale}px`;
    }
    window.addEventListener("resize", fitCanvas);
    function show(job) {
        if (active && active.id === job.id) return;
        cancelAnimationFrame(animation); active = job; finalShown = false;
        anchor = performance.now() - job.elapsed_ms;
        canvas.width = job.recording.width || 800;
        canvas.height = job.recording.height || 600;
        canvas.style.width = "";
        canvas.style.height = "";
        donor.hidden = !job.options.show_donor;
        donor.textContent = `${job.nickname}님 · ${Number(job.amount).toLocaleString("ko-KR")}원`;
        overlay.hidden = false;
        fitCanvas();
        function frame() {
            if (active !== job) return;
            const elapsed = performance.now() - anchor, replayMs = job.options.replay_seconds * 1000;
            if (elapsed >= replayMs + job.options.hold_seconds * 1000) {
                overlay.hidden = true; animation = 0; return;
            }
            if (elapsed < replayMs) {
                DrawingCanvas.render(canvas, job.recording, DrawingCanvas.duration(job.recording) * Math.max(0, elapsed / replayMs));
            } else if (!finalShown) {
                finalShown = true; DrawingCanvas.render(canvas, job.recording);
                if (job.final_png) {
                    const image = new Image();
                    image.onload = () => { if (active === job && finalShown) canvas.getContext("2d").drawImage(image, 0, 0); };
                    image.src = job.final_png;
                }
            }
            animation = requestAnimationFrame(frame);
        }
        frame();
    }
    async function poll() {
        if (busy) return;
        busy = true;
        try {
            const path = config.poll_path + (active ? `?current=${encodeURIComponent(active.id)}` : "");
            const response = await fetch(path, {method: "POST", cache: "no-store"});
            if (!response.ok) throw new Error("오버레이 연결 실패");
            const data = await response.json();
            if (data.playback) show(data.playback);
            else if (!active || data.current_id !== active.id) { active = null; cancelAnimationFrame(animation); overlay.hidden = true; }
        } catch { /* 일시적인 연결 장애에서는 현재 재생을 유지하고 다음 주기에 다시 연결한다. */ }
        finally { busy = false; }
    }
    if (config.preview) {
        window.addEventListener("message", event => {
            if (event.origin !== location.origin || event.source !== parent || event.data?.type !== "drawing-demo") return;
            const actions = [];
            const options = event.data.options || config.options;
            const width = options.canvas_width || 800, height = options.canvas_height || 600;
            const radius = Math.min(width / 8, height / 3);
            for (let i = 0; i < 3; i++) {
                const points = [];
                for (let j = 0; j <= 60; j++) {
                    const angle = j / 60 * Math.PI * 2;
                    points.push({x: (i + 1) * width / 4 + Math.cos(angle) * radius,
                        y: height / 2 + Math.sin(angle) * radius, t: i * 2000 + j * 30});
                }
                actions.push({type: "stroke", tool: "pen", color: ["#246544", "#dfa348", "#698bb2"][i], width: 12, points});
            }
            show({id: crypto.randomUUID(), recording: {width, height, actions}, elapsed_ms: 0,
                nickname: "테스트 시청자", amount: 1000, options});
        });
    } else { poll(); setInterval(poll, 1000); }
})();
