/* 보기 배율과 이동은 화면에만 적용하고 원본 캔버스·재생 좌표를 유지한다. */
window.DrawingView = class {
    constructor(canvas, state) {
        this.canvas = canvas; this.state = state;
        this.viewport = document.getElementById("drawingViewport");
        this.stage = document.getElementById("drawingCanvasStage");
        this.cursor = document.getElementById("drawingBrushCursor");
        this.zoom = 1; this.pan = false; this.drag = null; this.hover = null;
        this.focusButton = document.getElementById("focusDrawing");
        this.panButton = document.getElementById("panDrawing");
        this.zoomIn = document.getElementById("zoomInDrawing");
        this.zoomOut = document.getElementById("zoomOutDrawing");
        this.fitButton = document.getElementById("fitDrawing");
        this.zoomIn.addEventListener("click", () => this.setZoom(this.zoom * 1.5));
        this.zoomOut.addEventListener("click", () => this.setZoom(this.zoom / 1.5));
        this.fitButton.addEventListener("click", () => {
            this.setZoom(1); this.setPan(false);
            this.viewport.scrollTo(0, 0);
        });
        this.panButton.addEventListener("click", () => this.setPan(!this.pan));
        this.focusButton.addEventListener("click", () => this.setFocus(!document.body.classList.contains("drawing-focus")));
        window.addEventListener("keydown", event => {
            if (event.key === "Escape" && !document.querySelector("dialog[open]") && !this.state.busy()) this.setFocus(false);
        });
        canvas.addEventListener("pointerdown", event => {
            const middle = event.pointerType === "mouse" && event.button === 1;
            if (middle) event.preventDefault();
            if ((!this.pan && !middle) || this.drag || this.state.busy() ||
                (event.pointerType === "mouse" && event.button !== 0 && !middle)) return;
            event.preventDefault();
            this.drag = {id: event.pointerId, pointerType: event.pointerType, button: event.button, buttons: middle ? 4 : 1, x: event.clientX, y: event.clientY,
                left: this.viewport.scrollLeft, top: this.viewport.scrollTop};
            canvas.setPointerCapture(event.pointerId); canvas.dataset.panning = "true";
            this.state.changed();
        });
        canvas.addEventListener("pointermove", event => {
            this.hover = {x: event.clientX, y: event.clientY, type: event.pointerType};
            if (this.drag?.id === event.pointerId) {
                if (event.pointerType === "mouse" && !(event.buttons & this.drag.buttons)) { end(event); return; }
                this.viewport.scrollLeft = this.drag.left + this.drag.x - event.clientX;
                this.viewport.scrollTop = this.drag.top + this.drag.y - event.clientY;
            }
            this.updateCursor();
        });
        const end = event => {
            if (this.drag?.id === event.pointerId) {
                this.drag = null; canvas.dataset.panning = "false";
                if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
                this.state.changed();
            }
            if (event.pointerType === "touch") this.hideCursor();
        };
        canvas.addEventListener("pointerup", end); canvas.addEventListener("pointercancel", end);
        canvas.addEventListener("mouseup", event => {
            if (this.drag?.pointerType === "mouse" && event.button === this.drag.button) end({pointerId: this.drag.id, pointerType: "mouse"});
        });
        canvas.addEventListener("auxclick", event => { if (event.button === 1) event.preventDefault(); });
        canvas.addEventListener("lostpointercapture", end);
        canvas.addEventListener("pointerleave", () => { this.hover = null; this.hideCursor(); });
        this.viewport.addEventListener("scroll", () => this.hideCursor());
        this.observer = new ResizeObserver(() => this.layout());
        this.observer.observe(this.viewport);
        window.addEventListener("resize", () => this.layout());
        this.layout();
    }
    setZoom(value) {
        if (this.state.busy() || this.drag) return;
        this.zoom = Math.max(1, Math.min(4, value)); this.layout(); this.update();
    }
    setPan(value) {
        if (this.state.busy() || this.drag) return;
        this.pan = value; this.canvas.dataset.pan = String(value);
        this.panButton.setAttribute("aria-pressed", String(value)); this.hideCursor();
    }
    setFocus(value) {
        if (this.state.busy() || this.drag) return;
        document.body.classList.toggle("drawing-focus", value);
        this.focusButton.setAttribute("aria-pressed", String(value));
        this.focusButton.textContent = value ? "집중 모드 종료" : "집중 모드";
        requestAnimationFrame(() => this.layout());
    }
    layout() {
        if (this.state.drawing() || this.drag) return;
        const viewport = this.viewport, rect = this.stage.getBoundingClientRect();
        const viewRect = viewport.getBoundingClientRect();
        const x = rect.width ? (viewRect.left + viewport.clientLeft + viewport.clientWidth / 2 - rect.left) / rect.width : .5;
        const y = rect.height ? (viewRect.top + viewport.clientTop + viewport.clientHeight / 2 - rect.top) / rect.height : .5;
        const focus = document.body.classList.contains("drawing-focus");
        const maxHeight = focus ? viewport.clientHeight : Math.max(180, window.innerHeight * .65);
        const width = Math.min(viewport.clientWidth, maxHeight * this.canvas.width / this.canvas.height);
        if (width <= 0) return;
        const height = width * this.canvas.height / this.canvas.width;
        if (!focus) viewport.style.height = `${height + 2}px`;
        this.stage.style.width = `${width * this.zoom}px`;
        this.stage.style.height = `${height * this.zoom}px`;
        viewport.scrollLeft = this.stage.offsetLeft + x * width * this.zoom - viewport.clientWidth / 2;
        viewport.scrollTop = this.stage.offsetTop + y * height * this.zoom - viewport.clientHeight / 2;
        this.hideCursor();
        document.getElementById("drawingZoom").value = `${Math.round(this.zoom * 100)}%`;
    }
    hideCursor() { this.cursor.hidden = true; this.canvas.classList.remove("brush-cursor-active"); }
    updateCursor() {
        const point = this.hover, rect = this.canvas.getBoundingClientRect();
        const viewportRect = this.viewport.getBoundingClientRect();
        if (!point || point.type === "touch" || this.pan || this.drag || this.state.locked() ||
            this.state.tool() === "fill" || point.x < Math.max(rect.left, viewportRect.left) ||
            point.x > Math.min(rect.right, viewportRect.right) || point.y < Math.max(rect.top, viewportRect.top) ||
            point.y > Math.min(rect.bottom, viewportRect.bottom)) {
            this.hideCursor(); return;
        }
        this.cursor.style.width = `${this.state.width() * rect.width / this.canvas.width}px`;
        this.cursor.style.height = `${this.state.width() * rect.height / this.canvas.height}px`;
        this.cursor.style.left = `${point.x}px`; this.cursor.style.top = `${point.y}px`;
        this.cursor.hidden = false; this.canvas.classList.add("brush-cursor-active");
    }
    update() {
        const busy = this.state.busy() || Boolean(this.drag);
        for (const button of [this.zoomIn, this.zoomOut, this.fitButton, this.panButton, this.focusButton]) button.disabled = busy;
        this.zoomIn.disabled ||= this.zoom >= 4; this.zoomOut.disabled ||= this.zoom <= 1;
        this.updateCursor();
    }
};
