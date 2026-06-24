const form = document.getElementById("overlayForm");
const cssInput = document.getElementById("customCss");
const statusEl = document.getElementById("status");
const preview = document.getElementById("preview");
const overlayUrl = document.getElementById("overlayUrl");
const modeButtons = document.querySelectorAll("[data-preview-mode]");
const presetForm = document.getElementById("presetForm");
const presetName = document.getElementById("presetName");
const presetList = document.getElementById("presetList");
const advancedCss = document.querySelector(".advanced-css");
const defaults = JSON.parse(document.getElementById("overlayStyleDefaults").textContent);
const currentOptions = JSON.parse(document.getElementById("overlayStyleCurrent").textContent);
let styleMode = JSON.parse(document.getElementById("overlayStyleMode").textContent) || "options";
let presets = JSON.parse(document.getElementById("overlayPresetData").textContent);
let previewMode = "sample";

function setStatus(message) {
    statusEl.textContent = message;
}

function previewSource() {
    const separator = overlayUrl.value.includes("?") ? "&" : "?";
    if (previewMode === "sample") {
        return `${overlayUrl.value}${separator}preview=1&t=${Date.now()}`;
    }
    return `${overlayUrl.value}${separator}t=${Date.now()}`;
}

function refreshPreview() {
    preview.src = previewSource();
}

function setPreviewMode(mode) {
    previewMode = mode;
    modeButtons.forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.previewMode === mode));
    });
    refreshPreview();
}

function setStyleMode(mode) {
    styleMode = mode === "custom" ? "custom" : "options";
    advancedCss.open = styleMode === "custom";
}

function setControlValues(options) {
    Object.entries({...defaults, ...options}).forEach(([key, value]) => {
        const input = form.elements[key];
        if (!input) return;
        if (input instanceof RadioNodeList) {
            Array.from(input).forEach((item) => {
                if (item.type === "checkbox") {
                    item.checked = Array.isArray(value) && value.includes(item.value);
                }
            });
        } else if (input.type === "checkbox") {
            input.checked = Boolean(value);
        } else if (Array.isArray(value)) {
            input.value = value.join("\n");
        } else {
            input.value = value;
        }
    });
}

function readLineList(value) {
    const seen = new Set();
    return value
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter((item) => {
            if (!item || seen.has(item)) return false;
            seen.add(item);
            return true;
        });
}

function getStyleOptions() {
    return {
        position: form.elements.position.value,
        font_size: Number(form.elements.font_size.value),
        max_width: Number(form.elements.max_width.value),
        gap: Number(form.elements.gap.value),
        padding: Number(form.elements.padding.value),
        message_padding_y: Number(form.elements.message_padding_y.value),
        message_padding_x: Number(form.elements.message_padding_x.value),
        radius: Number(form.elements.radius.value),
        background_color: form.elements.background_color.value,
        background_opacity: Number(form.elements.background_opacity.value),
        text_color: form.elements.text_color.value,
        name_color: form.elements.name_color.value,
        shadow_strength: Number(form.elements.shadow_strength.value),
        animation: form.elements.animation.value,
        show_name: form.elements.show_name.checked,
        bubble_style: form.elements.bubble_style.value,
        blocked_nicknames: readLineList(form.elements.blocked_nicknames.value),
        blocked_roles: Array.from(form.elements.blocked_roles)
            .filter((input) => input.checked)
            .map((input) => input.value),
        message_ttl_seconds: Number(form.elements.message_ttl_seconds.value),
    };
}

async function save() {
    const response = await fetch("/auth/dashboard/overlay", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            custom_css: styleMode === "custom" ? cssInput.value : "",
            is_active: true,
            style_mode: styleMode,
            style_options: getStyleOptions(),
        }),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "저장하지 못했습니다.");
    }
    return response.json();
}

async function resetOptions() {
    if (!confirm("모든 스타일 옵션을 기본값으로 초기화할까요?")) {
        return;
    }
    setControlValues(defaults);
    setStyleMode("options");
    cssInput.value = "";
    await save();
    setStatus("기본 옵션으로 초기화되었습니다.");
    refreshPreview();
}

function renderPresets() {
    presetList.innerHTML = "";
    if (!presets.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "저장된 프리셋이 없습니다.";
        presetList.append(empty);
        return;
    }

    presets.forEach((preset) => {
        const row = document.createElement("div");
        row.className = "preset-row";

        const name = document.createElement("strong");
        name.textContent = preset.name;

        const controls = document.createElement("div");
        controls.className = "preset-actions";

        const apply = document.createElement("button");
        apply.type = "button";
        apply.className = "primary";
        apply.textContent = "적용";
        apply.addEventListener("click", () => applyPreset(preset.id));

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "danger";
        remove.textContent = "삭제";
        remove.addEventListener("click", () => deletePreset(preset.id));

        controls.append(apply, remove);
        row.append(name, controls);
        presetList.append(row);
    });
}

async function savePreset(event) {
    event.preventDefault();
    const name = presetName.value.trim();
    if (!name) {
        setStatus("프리셋 이름을 입력해 주세요.");
        return;
    }

    const response = await fetch("/auth/dashboard/overlay/presets", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            name,
            custom_css: styleMode === "custom" ? cssInput.value : "",
            style_mode: styleMode,
            style_options: getStyleOptions(),
        }),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "프리셋을 저장하지 못했습니다.");
    }
    const data = await response.json();
    presets = [data.preset, ...presets.filter((preset) => preset.id !== data.preset.id)];
    presetName.value = "";
    renderPresets();
    setStatus("프리셋이 저장되었습니다.");
}

async function applyPreset(id) {
    const response = await fetch(`/auth/dashboard/overlay/presets/${id}/apply`, {method: "POST"});
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "프리셋을 적용하지 못했습니다.");
    }
    const data = await response.json();
    setControlValues(data.preset.style_options);
    setStyleMode(data.preset.style_mode);
    cssInput.value = data.preset.custom_css;
    setStatus(`'${data.preset.name}' 프리셋을 적용했습니다.`);
    refreshPreview();
}

async function deletePreset(id) {
    if (!confirm("이 프리셋을 삭제할까요?")) return;
    const response = await fetch(`/auth/dashboard/overlay/presets/${id}`, {method: "DELETE"});
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "프리셋을 삭제하지 못했습니다.");
    }
    presets = presets.filter((preset) => preset.id !== id);
    renderPresets();
    setStatus("프리셋을 삭제했습니다.");
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        await save();
        setStatus("저장되었습니다.");
        refreshPreview();
    } catch (error) {
        setStatus(error.message);
    }
});

presetForm.addEventListener("submit", (event) => {
    savePreset(event).catch((error) => setStatus(error.message));
});

advancedCss.addEventListener("toggle", () => {
    styleMode = advancedCss.open ? "custom" : "options";
});

document.getElementById("refreshPreview").addEventListener("click", refreshPreview);

document.getElementById("resetOptions").addEventListener("click", () => {
    resetOptions().catch((error) => setStatus(error.message));
});

modeButtons.forEach((button) => {
    button.addEventListener("click", () => setPreviewMode(button.dataset.previewMode));
});

document.getElementById("copyUrl").addEventListener("click", async () => {
    await navigator.clipboard.writeText(overlayUrl.value);
    setStatus("링크를 복사했습니다.");
});

document.getElementById("rotateToken").addEventListener("click", async () => {
    if (!confirm("기존 OBS 링크가 더 이상 동작하지 않습니다. 재발급할까요?")) {
        return;
    }
    try {
        const response = await fetch("/auth/dashboard/overlay/token", {method: "POST"});
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || "링크를 재발급하지 못했습니다.");
        }
        const data = await response.json();
        overlayUrl.value = data.overlay_url;
        setStatus("새 링크가 발급되었습니다.");
        refreshPreview();
    } catch (error) {
        setStatus(error.message);
    }
});

setControlValues(currentOptions);
setStyleMode(styleMode);
renderPresets();
