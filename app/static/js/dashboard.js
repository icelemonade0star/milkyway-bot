const dashboardLimits = JSON.parse(document.getElementById("dashboardLimits").textContent);
const MAX_CHAT_RESPONSE_CHARS = Number(dashboardLimits.max_chat_response_chars);

function setStatus(resource, message) {
    const target = document.querySelector(`[data-status="${resource}"]`);
    if (target) target.textContent = message;
}

function assertResponseLength(response) {
    const parts = response.split("|").map((part) => part.trim()).filter(Boolean);
    const targets = parts.length ? parts : [response.trim()];
    const tooLong = targets.some((part) => part.length > MAX_CHAT_RESPONSE_CHARS);
    if (tooLong) {
        throw new Error(`응답은 구분자(|)로 나눈 각 항목이 ${MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다.`);
    }
}

function assertSingleResponseLength(response, label) {
    if (response.trim().length > MAX_CHAT_RESPONSE_CHARS) {
        throw new Error(`${label}은 ${MAX_CHAT_RESPONSE_CHARS}자 이하여야 합니다.`);
    }
}

function normalizeRequiredText(value, label) {
    const normalized = value.trim();
    if (!normalized) {
        throw new Error(`${label}을 입력해주세요.`);
    }
    return normalized;
}

function buildAttendanceResponse(checkedResponse, alreadyCheckedResponse, notStreamingResponse) {
    const checked = normalizeRequiredText(checkedResponse, "출석 응답");
    const alreadyChecked = normalizeRequiredText(alreadyCheckedResponse, "중복출석 응답");
    const notStreaming = notStreamingResponse.trim();

    assertSingleResponseLength(checked, "출석 응답");
    assertSingleResponseLength(alreadyChecked, "중복출석 응답");
    if (notStreaming) {
        assertSingleResponseLength(notStreaming, "방송 중 아님 응답");
    }

    const payload = {
        checked,
        already_checked: alreadyChecked,
    };
    if (notStreaming) {
        payload.not_streaming = notStreaming;
    }
    return JSON.stringify(payload);
}

function collectAttendanceResponse(container) {
    return buildAttendanceResponse(
        container.querySelector("[name='checked_response']").value,
        container.querySelector("[name='already_checked_response']").value,
        container.querySelector("[name='not_streaming_response']").value,
    );
}

function normalizeTrigger(value, label) {
    const parts = value.trim().split("|").map((part) => part.trim());
    if (!parts.length || parts.some((part) => !part)) {
        throw new Error(`${label}을 입력해주세요.`);
    }
    if (parts.some((part) => part.length < 2)) {
        throw new Error(`${label}는 2글자 이상이어야 합니다.`);
    }
    if (parts.some((part) => /\s/.test(part))) {
        throw new Error(`${label}에는 공백을 사용할 수 없습니다.`);
    }
    return parts.join("|");
}

function formatRequestError(data) {
    if (typeof data.detail === "string") {
        return data.detail;
    }
    if (Array.isArray(data.detail)) {
        const message = data.detail
            .map((item) => item.msg)
            .find((itemMessage) => typeof itemMessage === "string" && itemMessage);
        if (message) {
            return message.replace(/^Value error, /, "");
        }
    }
    return data.error || "요청을 처리할 수 없습니다.";
}

async function request(resource, method, body) {
    if (method === "POST") {
        if (body.command !== undefined) {
            body.command = normalizeTrigger(body.command, "명령어");
        }
        if (body.keyword !== undefined) {
            body.keyword = normalizeTrigger(body.keyword, "키워드");
        }
        if (body.response !== undefined) {
            body.response = normalizeRequiredText(body.response, "응답");
        }
        if (body.type !== undefined && !["text", "attendance"].includes(body.type)) {
            throw new Error("지원하지 않는 명령어 타입입니다.");
        }
    }

    if (method === "POST" && body.response && body.type !== "attendance") {
        assertResponseLength(body.response);
    }

    const response = await fetch(`/auth/dashboard/${resource}`, {
        method,
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(formatRequestError(data));
    }

    return response.json();
}

document.querySelectorAll("form.editor").forEach((form) => {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const resource = form.dataset.resource;
        const statusResource = form.dataset.statusResource || resource;
        const data = Object.fromEntries(new FormData(form).entries());
        if (data.type === "attendance") {
            data.response = collectAttendanceResponse(form);
            delete data.checked_response;
            delete data.already_checked_response;
            delete data.not_streaming_response;
        }

        try {
            await request(resource, "POST", data);
            setStatus(statusResource, "저장되었습니다. 화면을 새로고침합니다.");
            location.reload();
        } catch (error) {
            setStatus(statusResource, error.message);
        }
    });
});

document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
        const row = button.closest("tr");
        const resource = row.dataset.resource;
        const statusResource = row.dataset.statusResource || resource;
        const key = row.dataset.key;
        const action = button.dataset.action;

        try {
            if (action === "save") {
                const field = resource === "commands" ? "command" : "keyword";
                const body = {
                    [field]: key,
                    response: "",
                };
                if (resource === "commands") {
                    body.type = row.dataset.commandType || "text";
                    body.response = body.type === "attendance"
                        ? collectAttendanceResponse(row)
                        : row.querySelector("[name='response']").value;
                    body.cooldown_seconds = Number(row.querySelector("[name='cooldown_seconds']").value || 0);
                    body.is_active = row.querySelector("[name='is_active']").checked;
                } else {
                    body.response = row.querySelector("[name='response']").value;
                }
                await request(resource, "POST", body);
                setStatus(statusResource, "저장되었습니다.");
            } else if (confirm("삭제할까요?")) {
                await request(resource, "DELETE", {key});
                row.remove();
                setStatus(statusResource, "삭제되었습니다.");
            }
        } catch (error) {
            setStatus(statusResource, error.message);
        }
    });
});
