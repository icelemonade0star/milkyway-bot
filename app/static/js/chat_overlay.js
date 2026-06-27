const overlay = document.getElementById("chatOverlay");
const config = JSON.parse(document.getElementById("chatOverlayConfig").textContent);
const overlayRoot = document.querySelector(".chat-overlay");
const overlayStyle = getComputedStyle(overlayRoot);
const HARD_MAX_MESSAGES = 300;
const MAX_MESSAGE_TTL_MS = 3600000;
const configuredMessageTtlMs = Number(overlayStyle.getPropertyValue("--overlay-message-ttl-ms")) || 16000;
const messageTtlMs = Math.min(configuredMessageTtlMs, MAX_MESSAGE_TTL_MS);
const nameColorMode = overlayStyle.getPropertyValue("--overlay-name-color-mode").trim();
const nameColorPalette = overlayStyle.getPropertyValue("--overlay-name-color-palette")
    .split(",")
    .map((color) => color.trim())
    .filter(Boolean);
const streamerNameColor = overlayStyle.getPropertyValue("--overlay-streamer-name-color").trim() || "#FFD700";
const managerNameColor = overlayStyle.getPropertyValue("--overlay-manager-name-color").trim() || "#FF6B6B";
const isPreview = new URLSearchParams(location.search).has("preview");
const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
const socket = new WebSocket(`${wsProtocol}//${location.host}${config.websocket_path}`);
const hexColorPattern = /^#[0-9a-fA-F]{6}$/;

function randomNameColor() {
    if (nameColorMode !== "random" || !nameColorPalette.length) {
        return "";
    }
    return nameColorPalette[Math.floor(Math.random() * nameColorPalette.length)];
}

function resolveNameColor(payload) {
    const role = String(payload.role || "").toLowerCase();
    if (role === "streamer") {
        return streamerNameColor;
    }
    if (role === "channel_manager" || role === "manager") {
        return managerNameColor;
    }
    if (isPreview && hexColorPattern.test(payload.name_color || "")) {
        return payload.name_color;
    }
    if (hexColorPattern.test(payload.nickname_color || "")) {
        return payload.nickname_color;
    }
    return randomNameColor();
}

function addMessage(payload) {
    const item = document.createElement("div");
    item.className = "chat-message";

    const name = document.createElement("span");
    name.className = "chat-name";
    if (payload.badge_url) {
        const badge = document.createElement("img");
        badge.className = "chat-badge";
        badge.src = payload.badge_url;
        badge.alt = "";
        name.appendChild(badge);
    }
    name.appendChild(document.createTextNode(payload.nickname || "익명"));
    const nameColor = resolveNameColor(payload);
    if (nameColor) {
        name.style.color = nameColor;
    }

    const text = document.createElement("span");
    text.className = "chat-text";
    text.textContent = payload.message || "";

    item.append(name, text);
    overlay.appendChild(item);

    while (overlay.children.length > HARD_MAX_MESSAGES) {
        overlay.firstElementChild.remove();
    }

    window.setTimeout(() => item.remove(), messageTtlMs);
}

socket.addEventListener("message", (event) => {
    try {
        addMessage(JSON.parse(event.data));
    } catch (error) {
        console.error(error);
    }
});

window.addEventListener("message", (event) => {
    if (!isPreview || event.origin !== window.location.origin) {
        return;
    }
    if (event.data?.type === "milkyway-overlay-sample-chat") {
        const payload = event.data.payload;
        if (!payload || !String(payload.message || "").trim()) {
            return;
        }
        addMessage(payload);
    }
});

if (isPreview) {
    [
        {nickname: "Milkyway", message: "설정을 적용하면 이 미리보기에 바로 반영됩니다."},
        {nickname: "Viewer", message: "닉네임 색상, 말풍선, 글자 크기를 자유롭게 바꿔보세요."},
        {nickname: "Streamer", message: "OBS 링크에는 실제 채팅만 표시됩니다."},
    ].forEach((sample, index) => {
        window.setTimeout(() => addMessage(sample), index * 450);
    });
}
