/* 채널별 초안은 이 브라우저의 IndexedDB에만 보관한다. */
window.DrawingDraft = class {
    constructor(key) {
        this.key = key; this.db = null;
        this.ready = new Promise((resolve, reject) => {
            const request = indexedDB.open("milkyway-drawing", 1);
            request.onupgradeneeded = () => request.result.createObjectStore("drafts");
            request.onsuccess = () => {
                this.db = request.result;
                this.db.onversionchange = () => this.db.close();
                resolve();
            };
            request.onerror = () => reject(request.error);
            request.onblocked = () => reject(new Error("임시 저장소가 잠겨 있어요."));
        });
    }
    async transaction(mode, operation) {
        await this.ready;
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction("drafts", mode);
            const request = operation(transaction.objectStore("drafts"));
            transaction.oncomplete = () => resolve(request.result);
            transaction.onerror = transaction.onabort = () => reject(transaction.error || new Error("임시 저장 실패"));
        });
    }
    read() { return this.transaction("readonly", store => store.get(this.key)); }
    write(value) { return this.transaction("readwrite", store => store.put(value, this.key)); }
    remove() { return this.transaction("readwrite", store => store.delete(this.key)); }
    static valid(value) {
        const recording = value?.recording;
        if (value?.version !== 1 || typeof value.saveKey !== "string" ||
            !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value.saveKey) ||
            !Number.isInteger(recording?.width) || recording.width < 320 || recording.width > 1920 ||
            !Number.isInteger(recording.height) || recording.height < 180 || recording.height > 1080 ||
            !Array.isArray(recording.actions) || !recording.actions.length || recording.actions.length > 2000) return false;
        let count = 0, time = 0;
        for (const action of recording.actions) {
            if (action?.type !== "stroke" || !["pen", "eraser", "fill"].includes(action.tool) ||
                !/^#[a-f0-9]{6}$/i.test(action.color) || !Number.isFinite(action.width) || action.width < 1 || action.width > 60 ||
                !Array.isArray(action.points) || !action.points.length || (action.tool === "fill" && action.points.length !== 1)) return false;
            count += action.points.length;
            if (count > 25000) return false;
            for (const point of action.points) {
                if (!Number.isFinite(point?.x) || point.x < 0 || point.x > recording.width ||
                    !Number.isFinite(point.y) || point.y < 0 || point.y > recording.height ||
                    !Number.isInteger(point.t) || point.t < time || point.t > 600000) return false;
                time = point.t;
            }
        }
        return true;
    }
};
