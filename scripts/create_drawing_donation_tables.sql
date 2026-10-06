-- 그림 도네이션 신규 테이블. 기존 테이블과 데이터를 변경하지 않는다.
BEGIN;
CREATE TABLE IF NOT EXISTS v2_drawing_donation_settings (
    channel_id UUID PRIMARY KEY REFERENCES v2_channels(id) ON DELETE CASCADE,
    overlay_token VARCHAR(64) NOT NULL UNIQUE,
    options JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS v2_donation_drawings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    save_key UUID NOT NULL UNIQUE,
    hashtag VARCHAR(32) NOT NULL UNIQUE,
    recording JSONB NOT NULL,
    final_png TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_v2_donation_drawings_channel_id ON v2_donation_drawings(channel_id);
CREATE INDEX IF NOT EXISTS ix_v2_donation_drawings_expires_at ON v2_donation_drawings(expires_at);
CREATE TABLE IF NOT EXISTS v2_drawing_donation_queue (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    drawing_id UUID NOT NULL REFERENCES v2_donation_drawings(id) ON DELETE CASCADE,
    nickname VARCHAR(255) NOT NULL,
    amount BIGINT NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    playback JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_drawing_donation_queue_status CHECK (status IN ('queued', 'playing', 'done'))
);
CREATE INDEX IF NOT EXISTS idx_drawing_donation_queue_channel_status
ON v2_drawing_donation_queue(channel_id, status, created_at);
COMMIT;
