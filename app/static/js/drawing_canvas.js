(() => {
    "use strict";
    function visibleStrokes(recording, time = Infinity) {
        let strokes = [];
        for (const action of recording.actions) {
            if (action.type === "stroke") {
                const points = action.points.filter(point => point.t <= time);
                if (!points.length) break;
                strokes.push({...action, points});
            } else {
                if (action.t > time) break;
                if (action.type === "clear") strokes = [];
                if (action.type === "undo") strokes.pop();
            }
        }
        return strokes;
    }
    function stroke(ctx, action) {
        ctx.strokeStyle = ctx.fillStyle = action.tool === "eraser" ? "#ffffff" : action.color;
        ctx.lineWidth = action.width;
        ctx.lineCap = ctx.lineJoin = "round";
        const first = action.points[0];
        ctx.beginPath(); ctx.arc(first.x, first.y, action.width / 2, 0, Math.PI * 2); ctx.fill();
        if (action.points.length < 2) return;
        ctx.beginPath(); ctx.moveTo(first.x, first.y);
        for (const point of action.points.slice(1)) ctx.lineTo(point.x, point.y);
        ctx.stroke();
    }
    function render(canvas, recording, time = Infinity) {
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
        for (const action of visibleStrokes(recording, time)) stroke(ctx, action);
    }
    function duration(recording) {
        const action = recording.actions.at(-1);
        return action ? (action.type === "stroke" ? action.points.at(-1).t : action.t) : 0;
    }
    window.DrawingCanvas = {render, stroke, duration, visibleStrokes};
})();
