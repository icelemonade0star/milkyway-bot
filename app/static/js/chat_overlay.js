const overlay = document.getElementById("chatOverlay");
const config = JSON.parse(document.getElementById("chatOverlayConfig").textContent);
const overlayStyle = getComputedStyle(overlay);
const HARD_MAX_MESSAGES = 300;
const MAX_MESSAGE_TTL_MS = 3600000;
const configuredMessageTtlMs = Number(overlayStyle.getPropertyValue("--overlay-message-ttl-ms")) || 16000;
const messageTtlMs = Math.min(configuredMessageTtlMs, MAX_MESSAGE_TTL_MS);
const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
const socket = new WebSocket(`${wsProtocol}//${location.host}/overlay/ws/${config.token}`);

function addMessage(payload) {
    const item = document.createElement("div");
    item.className = "chat-message";

    const name = document.createElement("span");
    name.className = "chat-name";
    name.textContent = payload.nickname || "익명";

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

if (new URLSearchParams(location.search).has("preview")) {
    [
        {nickname: "Milkyway", message: "CSS를 저장하면 이 미리보기에 바로 반영됩니다."},
        {nickname: "Viewer", message: "닉네임 색상, 말풍선, 글자 크기를 자유롭게 바꿔보세요."},
        {nickname: "Streamer", message: "OBS 링크에는 실제 채팅만 표시됩니다."},
    ].forEach((sample, index) => {
        window.setTimeout(() => addMessage(sample), index * 450);
    });
}
