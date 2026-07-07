const form = document.getElementById("overlayForm");
const cssInput = document.getElementById("customCss");
const statusEl = document.getElementById("status");
const preview = document.getElementById("preview");
const overlayUrl = document.getElementById("overlayUrl");
const modeButtons = document.querySelectorAll("[data-preview-mode]");
const presetForm = document.getElementById("presetForm");
const presetName = document.getElementById("presetName");
const presetList = document.getElementById("presetList");
const paletteEditor = document.getElementById("nameColorPalette");
const paletteColorInput = document.getElementById("paletteColorInput");
const sampleChatForm = document.getElementById("sampleChatForm");
const sampleNickname = document.getElementById("sampleNickname");
const sampleMessage = document.getElementById("sampleMessage");
const advancedCss = document.querySelector('[data-section="css"]');
const defaults = JSON.parse(document.getElementById("overlayStyleDefaults").textContent);
const currentOptions = JSON.parse(document.getElementById("overlayStyleCurrent").textContent);
let styleMode = JSON.parse(document.getElementById("overlayStyleMode").textContent) || "options";
let presets = JSON.parse(document.getElementById("overlayPresetData").textContent);
let previewMode = "sample";
let syncingStyleMode = false;
let activePresetName = null;

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

function setSectionOpen(section, isOpen) {
    section.classList.toggle("is-collapsed", !isOpen);
    const button = section.querySelector(".section-toggle");
    if (button) {
        button.setAttribute("aria-expanded", String(isOpen));
    }
}

function setStyleMode(mode) {
    styleMode = mode === "custom" ? "custom" : "options";
    syncingStyleMode = true;
    setSectionOpen(advancedCss, styleMode === "custom");
    syncingStyleMode = false;
}

function formatRangeValue(name, value) {
    if (["font_size", "max_width"].includes(name)) return `${value}px`;
    if (name === "background_opacity") return `${value}%`;
    return value;
}

function updateRangeOutput(input) {
    const output = document.querySelector(`output[data-for="${input.name}"]`);
    if (output) {
        output.textContent = formatRangeValue(input.name, input.value);
    }
}

function updateAllRangeOutputs() {
    form.querySelectorAll('input[type="range"]').forEach(updateRangeOutput);
}

function setPaletteColors(colors) {
    const input = form.elements.name_color_palette;
    input.value = colors.join("\n");
    renderPalette();
}

function getPaletteColors() {
    return readLineList(form.elements.name_color_palette.value);
}

function renderPalette() {
    paletteEditor.innerHTML = "";
    const colors = getPaletteColors();
    if (!colors.length) {
        const empty = document.createElement("span");
        empty.className = "empty";
        empty.textContent = "적용 시 기본 색상이 자동으로 적용됩니다.";
        paletteEditor.append(empty);
        return;
    }

    colors.forEach((color) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "palette-chip";
        chip.style.backgroundColor = color;
        chip.title = `${color} 삭제`;
        chip.addEventListener("click", () => {
            setPaletteColors(getPaletteColors().filter((currentColor) => currentColor !== color));
        });
        paletteEditor.append(chip);
    });
}

function setControlValues(options) {
    Object.entries({...defaults, ...options}).forEach(([key, value]) => {
        const input = form.elements[key];
        if (!input) return;
        if (input instanceof RadioNodeList) {
            Array.from(input).forEach((item) => {
                if (item.type === "radio") {
                    item.checked = item.value === String(value);
                } else if (item.type === "checkbox") {
                    item.checked = Array.isArray(value) && value.includes(item.value);
                }
            });
        } else if (input.type === "checkbox") {
            input.checked = Boolean(value);
        } else if (Array.isArray(value)) {
            input.value = value.join("\n");
        } else if (key === "background_opacity") {
            input.value = 100 - Number(value);
        } else {
            input.value = value;
        }
    });
    updateAllRangeOutputs();
    updateNameGapVisibility();
    renderPalette();
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
        background_opacity: 100 - Number(form.elements.background_opacity.value),
        text_color: form.elements.text_color.value,
        name_color: form.elements.name_color.value,
        name_color_mode: form.elements.name_color_mode.value,
        name_color_palette: getPaletteColors(),
        shadow_strength: Number(form.elements.shadow_strength.value),
        animation: form.elements.animation.value,
        name_mode: form.elements.name_mode.value,
        name_gap: Number(form.elements.name_gap.value),
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
    const data = await response.json();
    if (data.style_options) {
        setControlValues(data.style_options);
    }
    if (data.style_mode) {
        setStyleMode(data.style_mode);
    }
    if (data.custom_css !== undefined) {
        cssInput.value = data.custom_css;
    }
    return data;
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

function sendSampleChat(nickname, message) {
    if (previewMode !== "sample") {
        setStatus("샘플 모드에서만 테스트 채팅을 보낼 수 있습니다.");
        return;
    }
    preview.contentWindow?.postMessage({
        type: "milkyway-overlay-sample-chat",
        payload: {nickname, message, name_color: getSampleNameColor()},
    }, window.location.origin);
}

function getSampleNameColor() {
    if (form.elements.name_color_mode.value !== "random") {
        return form.elements.name_color.value;
    }
    const colors = getPaletteColors();
    if (!colors.length) {
        return form.elements.name_color.value;
    }
    return colors[Math.floor(Math.random() * colors.length)];
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
    activePresetName = data.preset.name;
    document.getElementById("copyUrlWithPreset").disabled = false;
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
    const deleted = presets.find((p) => p.id === id);
    if (deleted && deleted.name === activePresetName) {
        activePresetName = null;
        document.getElementById("copyUrlWithPreset").disabled = true;
    }
    presets = presets.filter((preset) => preset.id !== id);
    renderPresets();
    setStatus("프리셋을 삭제했습니다.");
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        await save();
        setStatus("적용되었습니다.");
        refreshPreview();
    } catch (error) {
        setStatus(error.message);
    }
});

presetForm.addEventListener("submit", (event) => {
    savePreset(event).catch((error) => setStatus(error.message));
});

document.getElementById("refreshPreview").addEventListener("click", refreshPreview);

document.getElementById("resetOptions").addEventListener("click", () => {
    resetOptions().catch((error) => setStatus(error.message));
});

document.getElementById("addPaletteColor").addEventListener("click", () => {
    const color = paletteColorInput.value;
    const colors = getPaletteColors();
    if (!colors.includes(color)) {
        if (colors.length >= 20) {
            setStatus("색상은 최대 20개까지 추가할 수 있습니다.");
            return;
        }
        setPaletteColors([...colors, color]);
    }
});

sampleChatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (previewMode !== "sample") {
        setStatus("샘플 모드에서만 테스트 채팅을 보낼 수 있습니다.");
        return;
    }
    const nickname = sampleNickname.value.trim() || "익명";
    const message = sampleMessage.value.trim();
    if (!message) {
        setStatus("샘플 채팅 내용을 입력해 주세요.");
        return;
    }
    sendSampleChat(nickname, message);
    sampleMessage.value = "";
});

modeButtons.forEach((button) => {
    button.addEventListener("click", () => setPreviewMode(button.dataset.previewMode));
});

document.querySelectorAll(".section-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const section = button.closest(".settings-section");
        const willOpen = section.classList.contains("is-collapsed");
        setSectionOpen(section, willOpen);
        if (section === advancedCss && !syncingStyleMode) {
            styleMode = willOpen ? "custom" : "options";
        }
    });
});

function updateNameGapVisibility() {
    const isSeparate = form.elements.name_mode.value === "separate";
    document.getElementById("nameGapControl").classList.toggle("is-visible", isSeparate);
}

form.querySelectorAll('input[type="range"]').forEach((input) => {
    input.addEventListener("input", () => updateRangeOutput(input));
});

Array.from(form.elements.name_mode).forEach((radio) => {
    radio.addEventListener("change", updateNameGapVisibility);
});

document.getElementById("copyUrl").addEventListener("click", async () => {
    await navigator.clipboard.writeText(overlayUrl.value);
    setStatus("링크를 복사했습니다.");
});

document.getElementById("copyUrlWithPreset").addEventListener("click", async () => {
    if (!activePresetName) return;
    const url = `${overlayUrl.value}?preset=${encodeURIComponent(activePresetName)}`;
    await navigator.clipboard.writeText(url);
    setStatus(`'${activePresetName}' 프리셋 링크를 복사했습니다.`);
});

setControlValues(currentOptions);
setStyleMode(styleMode);
renderPresets();
