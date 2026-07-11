const form = document.getElementById("overlayForm");
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
const sampleTimerForm = document.getElementById("sampleTimerForm");
const sampleTimerCommand = document.getElementById("sampleTimerCommand");
const linkHint = document.getElementById("linkHint");
const overlayUrls = JSON.parse(document.getElementById("overlayUrls").textContent);

let previewMode = "sample";
let activeOverlayKind = "chat";
let activePresetName = null;
let sampleTimerState = null;
const syncingStyleMode = {chat: false, timer: false};
const MAX_TIMER_MS = 24 * 60 * 60 * 1000;

function parseJson(id) {
    return JSON.parse(document.getElementById(id).textContent);
}

function setStatus(message) {
    statusEl.textContent = message;
}

function getChatStyleOptions() {
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

function getTimerStyleOptions() {
    return {
        timer_autoplay: form.elements.timer_autoplay.checked,
        timer_auto_delete: form.elements.timer_auto_delete.checked,
        timer_auto_delete_delay_seconds: Number(form.elements.timer_auto_delete_delay_seconds.value),
        timer_display_mode: form.elements.timer_display_mode.value,
        timer_title_text: form.elements.timer_title_text.value.trim() || "타이머",
        timer_font_size: Number(form.elements.timer_font_size.value),
        timer_font_weight: form.elements.timer_font_weight.value,
        timer_text_color: form.elements.timer_text_color.value,
        timer_title_color: form.elements.timer_title_color.value,
        timer_done_color: form.elements.timer_done_color.value,
        timer_background_color: form.elements.timer_background_color.value,
        timer_background_opacity: Number(form.elements.timer_background_opacity.value),
        timer_global_opacity: Number(form.elements.timer_global_opacity.value),
    };
}

const KIND_CONFIG = {
    chat: {
        defaults: parseJson("chatStyleDefaults"),
        current: parseJson("chatStyleCurrent"),
        styleMode: parseJson("chatStyleMode") || "options",
        presets: parseJson("chatPresetData"),
        getOptions: getChatStyleOptions,
        cssTextarea: document.getElementById("customCss"),
        advancedCssSection: document.querySelector('[data-section="css"]'),
        saveUrl: "/auth/dashboard/overlay/chat",
        presetSaveUrl: "/auth/dashboard/overlay/chat/presets",
        presetApplyUrl: (id) => `/auth/dashboard/overlay/chat/presets/${id}/apply`,
        presetDeleteUrl: (id) => `/auth/dashboard/overlay/chat/presets/${id}`,
    },
    timer: {
        // 타이머는 프리셋을 지원하지 않습니다.
        defaults: parseJson("timerStyleDefaults"),
        current: parseJson("timerStyleCurrent"),
        styleMode: parseJson("timerStyleMode") || "options",
        getOptions: getTimerStyleOptions,
        cssTextarea: document.getElementById("timerCustomCss"),
        advancedCssSection: document.querySelector('[data-section="timer-css"]'),
        saveUrl: "/auth/dashboard/overlay/timer",
    },
};

function previewSource() {
    const baseUrl = overlayUrls[activeOverlayKind] || overlayUrls.chat;
    const separator = baseUrl.includes("?") ? "&" : "?";
    if (previewMode === "sample") {
        return `${baseUrl}${separator}preview=1&t=${Date.now()}`;
    }
    return `${baseUrl}${separator}t=${Date.now()}`;
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

function setOverlayKind(kind) {
    activeOverlayKind = kind === "timer" ? "timer" : "chat";
    document.querySelectorAll("[data-overlay-kind]").forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset.overlayKind === activeOverlayKind));
    });
    document.querySelectorAll("[data-overlay-pane]").forEach((section) => {
        section.classList.toggle("is-hidden", section.dataset.overlayPane !== activeOverlayKind);
    });
    overlayUrl.value = overlayUrls[activeOverlayKind] || overlayUrls.chat;
    sampleChatForm.hidden = activeOverlayKind !== "chat";
    sampleTimerForm.hidden = activeOverlayKind !== "timer";
    linkHint.textContent = activeOverlayKind === "timer"
        ? "OBS 브라우저 소스에 이 링크를 넣으면 방송 화면에 타이머가 표시됩니다."
        : "OBS 브라우저 소스에 이 링크를 넣으면 방송 화면에 채팅이 표시됩니다.";
    document.getElementById("copyUrlWithPreset").hidden = activeOverlayKind !== "chat";
    refreshPreview();
}

function setSectionOpen(section, isOpen) {
    section.classList.toggle("is-collapsed", !isOpen);
    const button = section.querySelector(".section-toggle");
    if (button) {
        button.setAttribute("aria-expanded", String(isOpen));
    }
}

function setStyleMode(kind, mode) {
    const config = KIND_CONFIG[kind];
    config.styleMode = mode === "custom" ? "custom" : "options";
    syncingStyleMode[kind] = true;
    setSectionOpen(config.advancedCssSection, config.styleMode === "custom");
    syncingStyleMode[kind] = false;
}

function formatRangeValue(name, value) {
    if (["font_size", "max_width", "timer_font_size"].includes(name)) return `${value}px`;
    if (["background_opacity", "timer_background_opacity", "timer_global_opacity"].includes(name)) return `${value}%`;
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

function setControlValues(kind, options) {
    const config = KIND_CONFIG[kind];
    Object.entries({...config.defaults, ...options}).forEach(([key, value]) => {
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
    if (kind === "chat") {
        updateNameGapVisibility();
        renderPalette();
    } else if (kind === "timer") {
        updateTimerTitleVisibility();
        updateTimerAutoDeleteVisibility();
    }
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

async function save(kind) {
    const config = KIND_CONFIG[kind];
    const response = await fetch(config.saveUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            custom_css: config.styleMode === "custom" ? config.cssTextarea.value : "",
            is_active: true,
            style_mode: config.styleMode,
            style_options: config.getOptions(),
        }),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "저장하지 못했습니다.");
    }
    const data = await response.json();
    if (data.style_options) {
        setControlValues(kind, data.style_options);
    }
    if (data.style_mode) {
        setStyleMode(kind, data.style_mode);
    }
    if (data.custom_css !== undefined) {
        config.cssTextarea.value = data.custom_css;
    }
    return data;
}

async function resetOptions(kind) {
    if (!confirm("모든 스타일 옵션을 기본값으로 초기화할까요?")) {
        return;
    }
    const config = KIND_CONFIG[kind];
    setControlValues(kind, config.defaults);
    setStyleMode(kind, "options");
    config.cssTextarea.value = "";
    await save(kind);
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

function parseTimerDuration(value) {
    const text = value.trim().toLowerCase();
    if (!text) {
        return null;
    }

    const clockParts = text.split(":");
    if (clockParts.length >= 2 && clockParts.length <= 3 && clockParts.every((part) => /^\d{1,2}$/.test(part))) {
        const numbers = clockParts.map(Number);
        const seconds = numbers.length === 3
            ? numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
            : numbers[0] * 60 + numbers[1];
        const minutes = numbers.length === 3 ? numbers[1] : numbers[0];
        const secondPart = numbers.length === 3 ? numbers[2] : numbers[1];
        const durationMs = seconds * 1000;
        return durationMs > 0 && durationMs <= MAX_TIMER_MS && minutes < 60 && secondPart < 60 ? durationMs : null;
    }

    if (/^\d+$/.test(text)) {
        const durationMs = Number(text) * 60 * 1000;
        return durationMs > 0 && durationMs <= MAX_TIMER_MS ? durationMs : null;
    }

    const unitPattern = /(\d+)\s*(시간|시|h|분|m|초|s)/gi;
    let totalSeconds = 0;
    let matched = false;
    let consumed = "";
    for (const match of text.matchAll(unitPattern)) {
        matched = true;
        consumed += match[0];
        const amount = Number(match[1]);
        const unit = match[2];
        if (["시간", "시", "h"].includes(unit)) totalSeconds += amount * 3600;
        if (["분", "m"].includes(unit)) totalSeconds += amount * 60;
        if (["초", "s"].includes(unit)) totalSeconds += amount;
    }
    if (matched) {
        const durationMs = totalSeconds * 1000;
        const normalizedConsumed = consumed.replace(/\s+/g, "");
        const normalizedText = text.replace(/\s+/g, "");
        return durationMs > 0 && durationMs <= MAX_TIMER_MS && normalizedConsumed === normalizedText ? durationMs : null;
    }

    return null;
}

function parseTimerCreateArgs(parts) {
    const durationText = parts.at(-1);
    const durationMs = parseTimerDuration(durationText);
    if (!durationMs) {
        return null;
    }
    return {
        title: parts.slice(0, -1).join(" ").trim(),
        durationMs,
    };
}

function currentSampleTimerRemaining() {
    if (!sampleTimerState) {
        return 0;
    }
    if (sampleTimerState.running && sampleTimerState.ends_at_ms) {
        return Math.max(0, sampleTimerState.ends_at_ms - Date.now());
    }
    return Math.max(0, Number(sampleTimerState.remaining_ms) || 0);
}

function getTimerDefaultTitle() {
    return form.elements.timer_title_text.value.trim() || "타이머";
}

function getSampleTimerRuntimeOptions() {
    return {
        timer_auto_delete: form.elements.timer_auto_delete.checked,
        timer_auto_delete_delay_seconds: Number(form.elements.timer_auto_delete_delay_seconds.value),
    };
}

function postSampleTimer(payload) {
    if (previewMode !== "sample" || activeOverlayKind !== "timer") {
        setStatus("샘플 모드에서만 테스트 타이머를 보낼 수 있습니다.");
        return false;
    }
    preview.contentWindow?.postMessage({
        type: "milkyway-overlay-sample-timer",
        payload: {...payload, options: getSampleTimerRuntimeOptions()},
    }, window.location.origin);
    return true;
}

function sendSampleTimer() {
    if (!sampleTimerState) {
        const durationMs = 25 * 60 * 1000;
        sampleTimerState = {
            title: getTimerDefaultTitle(),
            duration_ms: durationMs,
            remaining_ms: durationMs,
            running: false,
            started_at_ms: null,
            ends_at_ms: null,
        };
    }
    postSampleTimer({action: "snapshot", timer: {...sampleTimerState}});
}

function runSampleTimerCommand(command) {
    const normalized = command.trim().replace(/\s+/g, " ");
    if (!normalized.startsWith("!타이머")) {
        setStatus("!타이머 명령어를 입력해 주세요.");
        return;
    }

    const args = normalized.slice("!타이머".length).trim();
    if (!args) {
        setStatus("시간을 입력해 주세요.");
        return;
    }

    if (args === "삭제") {
        sampleTimerState = null;
        if (postSampleTimer({action: "delete"})) {
            setStatus("타이머 삭제 명령을 실행했습니다.");
        }
        return;
    }

    if (args === "정지") {
        if (!sampleTimerState) {
            setStatus("정지할 타이머가 없습니다.");
            return;
        }
        sampleTimerState = {
            ...sampleTimerState,
            remaining_ms: currentSampleTimerRemaining(),
            running: false,
            started_at_ms: null,
            ends_at_ms: null,
        };
        if (postSampleTimer({action: "snapshot", timer: {...sampleTimerState}})) {
            setStatus("타이머 정지 명령을 실행했습니다.");
        }
        return;
    }

    if (args === "재생") {
        if (!sampleTimerState) {
            setStatus("재생할 타이머가 없습니다.");
            return;
        }
        const remainingMs = currentSampleTimerRemaining();
        sampleTimerState = {
            ...sampleTimerState,
            remaining_ms: remainingMs,
            running: remainingMs > 0,
            started_at_ms: remainingMs > 0 ? Date.now() : null,
            ends_at_ms: remainingMs > 0 ? Date.now() + remainingMs : null,
        };
        if (postSampleTimer({action: "snapshot", timer: {...sampleTimerState}})) {
            setStatus("타이머 재생 명령을 실행했습니다.");
        }
        return;
    }

    const createArgs = parseTimerCreateArgs(args.split(" "));
    if (!createArgs) {
        setStatus("시간은 25:00, 10분, 30초 같은 형식으로 입력해 주세요.");
        return;
    }

    const shouldRun = form.elements.timer_autoplay.checked;
    sampleTimerState = {
        title: createArgs.title || getTimerDefaultTitle(),
        duration_ms: createArgs.durationMs,
        remaining_ms: createArgs.durationMs,
        running: shouldRun,
        started_at_ms: shouldRun ? Date.now() : null,
        ends_at_ms: shouldRun ? Date.now() + createArgs.durationMs : null,
    };
    if (postSampleTimer({action: "snapshot", timer: {...sampleTimerState}})) {
        setStatus("타이머 명령을 실행했습니다.");
    }
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
    const config = KIND_CONFIG.chat;
    presetList.innerHTML = "";
    if (!config.presets.length) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "저장된 프리셋이 없습니다.";
        presetList.append(empty);
        return;
    }

    config.presets.forEach((preset) => {
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

    const config = KIND_CONFIG.chat;
    const response = await fetch(config.presetSaveUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            name,
            custom_css: config.styleMode === "custom" ? config.cssTextarea.value : "",
            style_mode: config.styleMode,
            style_options: config.getOptions(),
        }),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "프리셋을 저장하지 못했습니다.");
    }
    const data = await response.json();
    config.presets = [data.preset, ...config.presets.filter((preset) => preset.id !== data.preset.id)];
    presetName.value = "";
    renderPresets();
    setStatus("프리셋이 저장되었습니다.");
}

async function applyPreset(id) {
    const config = KIND_CONFIG.chat;
    const response = await fetch(config.presetApplyUrl(id), {method: "POST"});
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "프리셋을 적용하지 못했습니다.");
    }
    const data = await response.json();
    setControlValues("chat", data.preset.style_options);
    setStyleMode("chat", data.preset.style_mode);
    config.cssTextarea.value = data.preset.custom_css;
    activePresetName = data.preset.name;
    document.getElementById("copyUrlWithPreset").disabled = false;
    setStatus(`'${data.preset.name}' 프리셋을 적용했습니다.`);
    refreshPreview();
}

async function deletePreset(id) {
    if (!confirm("이 프리셋을 삭제할까요?")) return;
    const config = KIND_CONFIG.chat;
    const response = await fetch(config.presetDeleteUrl(id), {method: "DELETE"});
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "프리셋을 삭제하지 못했습니다.");
    }
    const deleted = config.presets.find((p) => p.id === id);
    if (deleted && deleted.name === activePresetName) {
        activePresetName = null;
        document.getElementById("copyUrlWithPreset").disabled = true;
    }
    config.presets = config.presets.filter((preset) => preset.id !== id);
    renderPresets();
    setStatus("프리셋을 삭제했습니다.");
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        await save(activeOverlayKind);
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
    resetOptions(activeOverlayKind).catch((error) => setStatus(error.message));
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

sampleTimerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    runSampleTimerCommand(sampleTimerCommand.value);
});

document.querySelectorAll("[data-timer-command]").forEach((button) => {
    button.addEventListener("click", () => {
        sampleTimerCommand.value = button.dataset.timerCommand;
        runSampleTimerCommand(button.dataset.timerCommand);
    });
});

preview.addEventListener("load", () => {
    if (previewMode === "sample" && activeOverlayKind === "timer") {
        window.setTimeout(sendSampleTimer, 300);
    }
});

modeButtons.forEach((button) => {
    button.addEventListener("click", () => setPreviewMode(button.dataset.previewMode));
});

document.querySelectorAll("[data-overlay-kind]").forEach((button) => {
    button.addEventListener("click", () => setOverlayKind(button.dataset.overlayKind));
});

document.querySelectorAll(".section-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const section = button.closest(".settings-section");
        const willOpen = section.classList.contains("is-collapsed");
        setSectionOpen(section, willOpen);
        for (const kind of Object.keys(KIND_CONFIG)) {
            const config = KIND_CONFIG[kind];
            if (section === config.advancedCssSection && !syncingStyleMode[kind]) {
                config.styleMode = willOpen ? "custom" : "options";
            }
        }
    });
});

function updateNameGapVisibility() {
    const isSeparate = form.elements.name_mode.value === "separate";
    document.getElementById("nameGapControl").classList.toggle("is-visible", isSeparate);
}

function updateTimerTitleVisibility() {
    const isTitled = form.elements.timer_display_mode.value === "titled";
    document.getElementById("timerTitleControl").hidden = !isTitled;
}

function updateTimerAutoDeleteVisibility() {
    document.getElementById("timerDeleteDelayControl").hidden = !form.elements.timer_auto_delete.checked;
}

form.querySelectorAll('input[type="range"]').forEach((input) => {
    input.addEventListener("input", () => updateRangeOutput(input));
});

Array.from(form.elements.name_mode).forEach((radio) => {
    radio.addEventListener("change", updateNameGapVisibility);
});

Array.from(form.elements.timer_display_mode).forEach((radio) => {
    radio.addEventListener("change", updateTimerTitleVisibility);
});

form.elements.timer_auto_delete.addEventListener("change", updateTimerAutoDeleteVisibility);

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

setControlValues("chat", KIND_CONFIG.chat.current);
setControlValues("timer", KIND_CONFIG.timer.current);
setStyleMode("chat", KIND_CONFIG.chat.styleMode);
setStyleMode("timer", KIND_CONFIG.timer.styleMode);
setOverlayKind("chat");
renderPresets();
