() => {
    const api = window.DrawingCanvas;
    const canvas = () => { const c = document.createElement('canvas'); c.width = 400; c.height = 300; return c; };
    const bytes = c => c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    const differences = (a, b) => {
        const x = bytes(a), y = bytes(b);
        let count = 0;
        for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) count++;
        return count;
    };
    function incremental(c, actions) {
        const ctx = c.getContext('2d');
        for (const action of actions) {
            if (action.tool === 'fill') { api.fill(ctx, action.points[0].x, action.points[0].y, action.color); continue; }
            api.stroke(ctx, {...action, points: action.points.slice(0, 1)}, true);
            for (let i = 1; i < action.points.length; i++) api.stroke(ctx, {...action, points: action.points.slice(i - 1, i + 1)}, true);
        }
    }
    const action = (tool, width, color, points) => ({type: 'stroke', tool, width, color, points});
    let seed = 42;
    const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
    const editing = [];
    for (const tool of ['pen', 'eraser']) for (const width of [1, 3, 20, 60]) {
        const actions = tool === 'eraser' ? [action('fill', 1, '#8b4db0', [{x: 0, y: 0, t: 0}])] : [];
        for (let s = 0; s < 3; s++) {
            const points = Array.from({length: 18}, (_, i) => ({x: 20 + i * 20, y: 30 + random() * 240, t: (s * 18 + i + 1) * 10}));
            actions.push(action(tool, width, ['#8b4db0', '#ef3b3f', '#ffffff'][s], points));
        }
        const live = canvas(), replay = canvas();
        incremental(live, actions);
        api.render(replay, {actions}, Infinity, true);
        editing.push({tool, width, differences: differences(live, replay)});
    }
    const colorCanvas = canvas();
    api.render(colorCanvas, {actions: [action('pen', 20, '#8b4db0', [
        {x: 35.2, y: 21.7, t: 0}, {x: 361.8, y: 271.3, t: 100},
    ])]}, Infinity, true);
    const colorPixels = bytes(colorCanvas);
    let wrongColor = 0;
    for (let i = 0; i < colorPixels.length; i += 4) {
        if (colorPixels[i + 3] && (colorPixels[i] !== 139 || colorPixels[i + 1] !== 77 || colorPixels[i + 2] !== 176 || colorPixels[i + 3] !== 255)) wrongColor++;
    }
    const ringPoints = Array.from({length: 73}, (_, i) => {
        const angle = i / 72 * Math.PI * 2;
        return {x: 200 + Math.cos(angle) * 110, y: 150 + Math.sin(angle) * 90, t: i * 10};
    });
    const actions = [
        action('pen', 1, '#ffffff', ringPoints),
        action('fill', 1, '#8b4db0', [{x: 200, y: 150, t: 800}]),
        action('eraser', 10, '#ffffff', [{x: 180, y: 150, t: 900}, {x: 220, y: 150, t: 1000}]),
        action('fill', 1, '#ef3b3f', [{x: 200, y: 150, t: 1100}]),
        action('pen', 3, '#2f6ee5', [{x: 10, y: 10, t: 1200}, {x: 390, y: 290, t: 1300}]),
    ];
    const recording = {actions}, cached = canvas(), reference = canvas();
    const render = api.createRenderer(cached, recording, true);
    const times = [0, 250, 720, 800, 950, 1100, 1250, Infinity, 250, 1100, Infinity];
    const playback = times.map(time => {
        render(time); api.render(reference, recording, time, true);
        return {time: String(time), differences: differences(cached, reference)};
    });
    const live = canvas(); incremental(live, actions);
    const finalDifferences = differences(live, cached);
    const prototype = CanvasRenderingContext2D.prototype;
    const originalRead = prototype.getImageData, originalFill = prototype.fillRect;
    let repeatedReads = 0, repeatedStrokes = 0;
    try {
        prototype.getImageData = function(...args) { repeatedReads++; return originalRead.apply(this, args); };
        prototype.fillRect = function(...args) { repeatedStrokes++; return originalFill.apply(this, args); };
        render(Infinity); render(Infinity);
    } finally {
        prototype.getImageData = originalRead; prototype.fillRect = originalFill;
    }
    return {editing, wrongColor, playback, finalDifferences, repeatedReads, repeatedStrokes};
}
