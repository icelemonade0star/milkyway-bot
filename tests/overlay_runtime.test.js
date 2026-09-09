const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function runtime(file, preview = false) {
    let now = 0;
    let nextId = 0;
    const tasks = new Map();
    const frames = new Map();
    const events = {};
    const sockets = [];
    const elements = new Map();
    function element() {
        const classes = new Set();
        return {
            textContent: "", children: [], style: {},
            classList: {
                add: c => classes.add(c), remove: c => classes.delete(c),
                toggle: (c, value) => value ? classes.add(c) : classes.delete(c),
                contains: c => classes.has(c),
            },
            append(...children) { this.children.push(...children); },
            appendChild(child) { this.children.push(child); },
            remove() {},
        };
    }
    const options = {timer_auto_delete: true, timer_auto_delete_delay_seconds: 0};
    for (const id of ["timerOverlay", "timerTitle", "timerTime", "chatOverlay", "overlayCustomStyle", "overlayRuntimeStyle"]) {
        elements.set(id, element());
    }
    for (const id of ["timerOverlayConfig", "chatOverlayConfig"]) {
        elements.set(id, {textContent: JSON.stringify({websocket_path: "/ws", options})});
    }
    class Socket {
        constructor(url) { this.url = url; this.events = {}; sockets.push(this); }
        addEventListener(name, fn) { this.events[name] = fn; }
        close() { this.events.close?.(); }
        send(payload) { this.events.message({data: JSON.stringify(payload)}); }
    }
    const context = vm.createContext({
        document: {
            getElementById: id => elements.get(id), querySelector: () => elements.get("chatOverlay"),
            createElement: element, createTextNode: text => ({textContent: text}),
        },
        getComputedStyle: () => ({getPropertyValue: () => ""}),
        location: {search: preview ? "?preview=1" : "", host: "localhost", protocol: "http:", origin: "http://localhost"},
        URLSearchParams, WebSocket: Socket, console, performance: {now: () => now},
        window: {
            location: {origin: "http://localhost"},
            addEventListener: (name, fn) => {events[name] = fn;},
            setTimeout: (fn, ms) => {tasks.set(++nextId, {fn, ms}); return nextId;},
            clearTimeout: id => tasks.delete(id),
            requestAnimationFrame: fn => {frames.set(++nextId, fn); return nextId;},
            cancelAnimationFrame: id => frames.delete(id),
        },
    });
    for (const script of ["overlay_socket.js", file]) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, "../app/static/js", script), "utf8"), context);
    }
    return {
        elements, sockets, tasks, events, context,
        advance: ms => {now += ms;},
        run: code => vm.runInContext(code, context),
        fire: () => {
            const [id, task] = tasks.entries().next().value;
            tasks.delete(id); task.fn(); return task.ms;
        },
    };
}

const snapshot = (remaining, id = "timer-1", action = "snapshot") => ({
    type: "timer", action, timer: {timer_id: id, remaining_ms: remaining, running: remaining > 0},
});

for (const file of ["timer_overlay.js", "chat_overlay.js"]) {
    test(`${file}: sample mode never opens live socket`, () => {
        const r = runtime(file, true);
        assert.equal(r.sockets.length, 0);
    });
    test(`${file}: reconnect backs off, resets on open, stops on pagehide`, () => {
        const r = runtime(file);
        r.sockets[0].close();
        assert.equal(r.fire(), 1000);
        r.sockets[1].close();
        assert.equal(r.fire(), 2000);
        r.sockets[2].events.open();
        r.sockets[2].close();
        assert.equal(r.fire(), 1000);
        r.events.pagehide();
        assert.equal(r.tasks.size, 0);
    });
}

test("timer: reconnect does not resurrect an auto-deleted timer; replay still works", () => {
    const r = runtime("timer_overlay.js");
    r.sockets[0].send(snapshot(0));
    r.fire(); r.fire();
    assert(!r.elements.get("timerOverlay").classList.contains("is-visible"));
    r.sockets[0].send(snapshot(0, "timer-1", "sync"));
    assert(!r.elements.get("timerOverlay").classList.contains("is-visible"));
    r.sockets[0].send(snapshot(120000, "timer-2", "sync"));
    assert(r.elements.get("timerOverlay").classList.contains("is-visible"));
    assert.equal(r.run("currentTimerRemaining()"), 120000);
});

test("timer: sync during fade keeps deletion schedule", () => {
    const r = runtime("timer_overlay.js");
    r.sockets[0].send(snapshot(0)); r.fire();
    const pending = [...r.tasks.keys()];
    r.sockets[0].send(snapshot(0, "timer-1", "sync"));
    assert.deepEqual([...r.tasks.keys()], pending);
    assert(r.elements.get("timerOverlay").classList.contains("is-fading"));
});

test("timer: live settings preserve countdown and cancel disabled auto-delete", () => {
    const r = runtime("timer_overlay.js");
    r.sockets[0].send(snapshot(120000));
    r.advance(20000);
    r.sockets[0].send({type: "overlay-settings", custom_css: "new css", options: {
        timer_auto_delete: true, timer_auto_delete_delay_seconds: 0,
    }});
    assert.equal(r.run("currentTimerRemaining()"), 100000);
    assert.equal(r.elements.get("overlayCustomStyle").textContent, "new css");
    r.sockets[0].send(snapshot(0)); r.fire();
    r.sockets[0].send({type: "overlay-settings", custom_css: "new css", options: {
        timer_auto_delete: false, timer_auto_delete_delay_seconds: 0,
    }});
    assert.equal(r.tasks.size, 0);
    assert(!r.elements.get("timerOverlay").classList.contains("is-fading"));
});

test("chat: settings messages update CSS without adding a chat message", () => {
    const r = runtime("chat_overlay.js");
    r.sockets[0].send({type: "overlay-settings", custom_css: "new css", options: {
        message_ttl_seconds: 3, name_color_mode: "fixed", name_color_palette: ["#ffffff"],
    }});
    assert.equal(r.elements.get("chatOverlay").children.length, 0);
    assert.equal(r.elements.get("overlayCustomStyle").textContent, "new css");
    r.sockets[0].send({nickname: "viewer", message: "hello"});
    assert.equal(r.elements.get("chatOverlay").children.length, 1);
    assert.equal(r.fire(), 3000);
});
