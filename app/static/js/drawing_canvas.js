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
    function segment(ctx, from, to, width) {
        // 정수 픽셀 구간으로 둥근 선을 그려 반투명 경계와 화면 픽셀 읽기를 없앤다.
        // 픽셀 대각선의 반만큼 확장하여 1px 폐곡선도 채우기 경계로 이어지게 한다.
        const radius = width / 2 + Math.SQRT1_2;
        const dx = to.x - from.x, dy = to.y - from.y, length = Math.hypot(dx, dy);
        const nx = length ? -dy / length * radius : 0, ny = length ? dx / length * radius : 0;
        const corners = [
            {x: from.x + nx, y: from.y + ny}, {x: to.x + nx, y: to.y + ny},
            {x: to.x - nx, y: to.y - ny}, {x: from.x - nx, y: from.y - ny},
        ];
        const firstRow = Math.max(0, Math.ceil(Math.min(from.y, to.y) - radius - 0.5));
        const lastRow = Math.min(ctx.canvas.height - 1, Math.floor(Math.max(from.y, to.y) + radius - 0.5));
        for (let y = firstRow; y <= lastRow; y++) {
            const centerY = y + 0.5;
            let left = Infinity, right = -Infinity;
            for (const point of [from, to]) {
                const distanceY = centerY - point.y;
                if (Math.abs(distanceY) > radius) continue;
                const half = Math.sqrt(Math.max(0, radius * radius - distanceY * distanceY));
                left = Math.min(left, point.x - half); right = Math.max(right, point.x + half);
            }
            if (length) for (let i = 0; i < corners.length; i++) {
                const a = corners[i], b = corners[(i + 1) % corners.length];
                if ((a.y <= centerY && b.y > centerY) || (b.y <= centerY && a.y > centerY)) {
                    const x = a.x + (centerY - a.y) / (b.y - a.y) * (b.x - a.x);
                    left = Math.min(left, x); right = Math.max(right, x);
                }
            }
            const firstColumn = Math.max(0, Math.ceil(left - 0.5));
            const lastColumn = Math.min(ctx.canvas.width - 1, Math.floor(right - 0.5));
            if (lastColumn >= firstColumn) ctx.fillRect(firstColumn, y, lastColumn - firstColumn + 1, 1);
        }
    }
    function stroke(ctx, action, transparent = false) {
        ctx.globalCompositeOperation = transparent && action.tool === "eraser" ? "destination-out" : "source-over";
        ctx.fillStyle = action.tool === "eraser" ? "#ffffff" : action.color;
        const first = action.points[0];
        segment(ctx, first, first, action.width);
        for (let i = 1; i < action.points.length; i++) segment(ctx, action.points[i - 1], action.points[i], action.width);
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
        if (actions.some(action => action.type !== "stroke")) {
            return time => render(canvas, recording, time, transparent);
        }
        const cache = document.createElement("canvas");
        cache.width = canvas.width; cache.height = canvas.height;
        const cacheContext = cache.getContext("2d"); clear(cacheContext, transparent);
        // 선 조각과 채우기는 앞으로 재생할 때 한 번만 처리한다. 역방향 재생은 캐시를 다시 만든다.
        let actionIndex = 0, pointIndex = 0, previousTime = -Infinity;
        return (time = Infinity) => {
            if (time < previousTime) {
                clear(cacheContext, transparent); actionIndex = 0; pointIndex = 0;
            }
            previousTime = time;
            while (actionIndex < actions.length) {
                const action = actions[actionIndex];
                if (action.points[pointIndex].t > time) break;
                if (action.tool === "fill") {
                    drawAction(cacheContext, action, transparent);
                    pointIndex = action.points.length;
                } else while (pointIndex < action.points.length && action.points[pointIndex].t <= time) {
                    const points = pointIndex ? action.points.slice(pointIndex - 1, pointIndex + 1) : action.points.slice(0, 1);
                    stroke(cacheContext, {...action, points}, transparent); pointIndex++;
                }
                if (pointIndex < action.points.length) break;
                actionIndex++; pointIndex = 0;
            }
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(cache, 0, 0);
        };
    }
    function duration(recording) {
        const action = recording.actions.at(-1);
        return action ? (action.type === "stroke" ? action.points.at(-1).t : action.t) : 0;
    }
    window.DrawingCanvas = {render, createRenderer, stroke, fill, duration, visibleStrokes};
})();
