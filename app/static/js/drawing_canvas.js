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
    function stroke(ctx, action, transparent = false) {
        ctx.globalCompositeOperation = transparent && action.tool === "eraser" ? "destination-out" : "source-over";
        ctx.strokeStyle = ctx.fillStyle = action.tool === "eraser" ? "#ffffff" : action.color;
        ctx.lineWidth = action.width;
        ctx.lineCap = ctx.lineJoin = "round";
        const first = action.points[0];
        ctx.beginPath(); ctx.arc(first.x, first.y, action.width / 2, 0, Math.PI * 2); ctx.fill();
        if (action.points.length >= 2) {
            ctx.beginPath(); ctx.moveTo(first.x, first.y);
            for (const point of action.points.slice(1)) ctx.lineTo(point.x, point.y);
            ctx.stroke();
        }
        ctx.globalCompositeOperation = "source-over";
    }
    function colorBytes(color) {
        return [parseInt(color.slice(1, 3), 16), parseInt(color.slice(3, 5), 16), parseInt(color.slice(5, 7), 16), 255];
    }
    function fill(ctx, x, y, color) {
        const width = ctx.canvas.width, height = ctx.canvas.height;
        const seedX = Math.max(0, Math.min(width - 1, Math.floor(x))), seedY = Math.max(0, Math.min(height - 1, Math.floor(y)));
        const image = ctx.getImageData(0, 0, width, height), pixels = image.data;
        const seed = (seedY * width + seedX) * 4, target = pixels.slice(seed, seed + 4), replacement = colorBytes(color);
        if (target.every((value, index) => Math.abs(value - replacement[index]) <= 8)) return;
        const matches = index => Math.abs(pixels[index] - target[0]) <= 8 && Math.abs(pixels[index + 1] - target[1]) <= 8 &&
            Math.abs(pixels[index + 2] - target[2]) <= 8 && Math.abs(pixels[index + 3] - target[3]) <= 8;
        const visited = new Uint8Array(width * height), seedPixel = seedY * width + seedX, stack = [seedPixel];
        visited[seedPixel] = 1;
        while (stack.length) {
            const pixel = stack.pop(), index = pixel * 4, currentX = pixel % width;
            if (!matches(index)) continue;
            pixels[index] = replacement[0]; pixels[index + 1] = replacement[1];
            pixels[index + 2] = replacement[2]; pixels[index + 3] = replacement[3];
            const neighbors = [pixel - 1, pixel + 1, pixel - width, pixel + width];
            for (const neighbor of neighbors) {
                const neighborX = neighbor % width;
                if (neighbor < 0 || neighbor >= width * height || (neighborX === width - 1 && currentX === 0) ||
                    (neighborX === 0 && currentX === width - 1) || visited[neighbor]) continue;
                const neighborIndex = neighbor * 4;
                if (matches(neighborIndex)) { visited[neighbor] = 1; stack.push(neighbor); }
            }
        }
        ctx.putImageData(image, 0, 0);
    }
    function clear(ctx, transparent) {
        if (transparent) ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        else { ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height); }
    }
    function drawAction(ctx, action, transparent) {
        if (action.tool === "fill") fill(ctx, action.points[0].x, action.points[0].y, action.color);
        else stroke(ctx, action, transparent);
    }
    function render(canvas, recording, time = Infinity, transparent = false) {
        const ctx = canvas.getContext("2d");
        clear(ctx, transparent);
        for (const action of visibleStrokes(recording, time)) {
            drawAction(ctx, action, transparent);
        }
    }
    function createRenderer(canvas, recording, transparent = false) {
        const actions = recording.actions;
        if (!actions.some(action => action.type === "stroke" && action.tool === "fill") || actions.some(action => action.type !== "stroke")) {
            return time => render(canvas, recording, time, transparent);
        }
        const cache = document.createElement("canvas");
        cache.width = canvas.width; cache.height = canvas.height;
        const cacheContext = cache.getContext("2d"); clear(cacheContext, transparent);
        const fillIndexes = actions.map((action, index) => action.tool === "fill" ? {index, time: action.points[0].t} : null).filter(Boolean);
        let preparedThrough = -1;
        return (time = Infinity) => {
            let targetFill = -1;
            for (const fillIndex of fillIndexes) {
                if (fillIndex.time <= time) targetFill = fillIndex.index;
                else break;
            }
            if (targetFill < preparedThrough) {
                clear(cacheContext, transparent); preparedThrough = -1;
            }
            if (targetFill > preparedThrough) {
                for (let index = preparedThrough + 1; index <= targetFill; index++) drawAction(cacheContext, actions[index], transparent);
                preparedThrough = targetFill;
            }
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(cache, 0, 0);
            for (let index = preparedThrough + 1; index < actions.length; index++) {
                const action = actions[index], points = action.points.filter(point => point.t <= time);
                if (!points.length) break;
                drawAction(ctx, {...action, points}, transparent);
            }
        };
    }
    function duration(recording) {
        const action = recording.actions.at(-1);
        return action ? (action.type === "stroke" ? action.points.at(-1).t : action.t) : 0;
    }
    window.DrawingCanvas = {render, createRenderer, stroke, fill, duration, visibleStrokes};
})();
