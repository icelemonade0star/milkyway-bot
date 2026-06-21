CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION v2_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS v2_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform VARCHAR(50) NOT NULL,
    platform_channel_id VARCHAR(255) NOT NULL,
    channel_name VARCHAR(255) NOT NULL,
    profile_image_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_platform_channel UNIQUE (platform, platform_channel_id)
);

DROP TRIGGER IF EXISTS trg_v2_channels_updated_at ON v2_channels;
CREATE TRIGGER trg_v2_channels_updated_at
BEFORE UPDATE ON v2_channels
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_platform_credentials (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    token_type VARCHAR(50),
    scope TEXT,
    raw_token_response JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_platform_credentials_channel_platform UNIQUE (channel_id, platform)
);

DROP TRIGGER IF EXISTS trg_v2_platform_credentials_updated_at ON v2_platform_credentials;
CREATE TRIGGER trg_v2_platform_credentials_updated_at
BEFORE UPDATE ON v2_platform_credentials
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_channel_configs (
    channel_id UUID PRIMARY KEY REFERENCES v2_channels(id) ON DELETE CASCADE,
    command_prefix VARCHAR(10) NOT NULL DEFAULT '!',
    language VARCHAR(10) NOT NULL DEFAULT 'ko',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DROP TRIGGER IF EXISTS trg_v2_channel_configs_updated_at ON v2_channel_configs;
CREATE TRIGGER trg_v2_channel_configs_updated_at
BEFORE UPDATE ON v2_channel_configs
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_global_chat_commands (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    command VARCHAR(100) NOT NULL,
    response TEXT,
    type VARCHAR(20) NOT NULL DEFAULT 'text',
    cooldown_seconds INTEGER NOT NULL DEFAULT 5,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_global_chat_commands_command UNIQUE (command)
);

DROP TRIGGER IF EXISTS trg_v2_global_chat_commands_updated_at ON v2_global_chat_commands;
CREATE TRIGGER trg_v2_global_chat_commands_updated_at
BEFORE UPDATE ON v2_global_chat_commands
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_channel_chat_commands (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    command VARCHAR(100) NOT NULL,
    response TEXT NOT NULL,
    type VARCHAR(20) NOT NULL DEFAULT 'text',
    cooldown_seconds INTEGER NOT NULL DEFAULT 5,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_channel_chat_commands_channel_command UNIQUE (channel_id, command)
);

DROP TRIGGER IF EXISTS trg_v2_channel_chat_commands_updated_at ON v2_channel_chat_commands;
CREATE TRIGGER trg_v2_channel_chat_commands_updated_at
BEFORE UPDATE ON v2_channel_chat_commands
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_channel_greetings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    keyword VARCHAR(100) NOT NULL,
    response TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_channel_greetings_channel_keyword UNIQUE (channel_id, keyword)
);

DROP TRIGGER IF EXISTS trg_v2_channel_greetings_updated_at ON v2_channel_greetings;
CREATE TRIGGER trg_v2_channel_greetings_updated_at
BEFORE UPDATE ON v2_channel_greetings
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_viewer_attendance (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    platform_user_id VARCHAR(255) NOT NULL,
    user_name VARCHAR(255),
    attendance_count INTEGER NOT NULL DEFAULT 1,
    streak_count INTEGER NOT NULL DEFAULT 1,
    last_attendance_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_viewer_attendance_channel_user UNIQUE (channel_id, platform_user_id)
);

DROP TRIGGER IF EXISTS trg_v2_viewer_attendance_updated_at ON v2_viewer_attendance;
CREATE TRIGGER trg_v2_viewer_attendance_updated_at
BEFORE UPDATE ON v2_viewer_attendance
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_stream_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL,
    closed_at TIMESTAMP WITH TIME ZONE,
    stream_title VARCHAR(255),
    category VARCHAR(255),
    thumbnail_url TEXT,
    raw_live_response JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_v2_stream_sessions_channel_opened_at UNIQUE (channel_id, opened_at)
);

CREATE INDEX IF NOT EXISTS idx_v2_stream_sessions_channel_opened_at
ON v2_stream_sessions(channel_id, opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_v2_stream_sessions_open
ON v2_stream_sessions(channel_id)
WHERE closed_at IS NULL;

DROP TRIGGER IF EXISTS trg_v2_stream_sessions_updated_at ON v2_stream_sessions;
CREATE TRIGGER trg_v2_stream_sessions_updated_at
BEFORE UPDATE ON v2_stream_sessions
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_channel_live_states (
    channel_id UUID PRIMARY KEY REFERENCES v2_channels(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    current_stream_session_id UUID REFERENCES v2_stream_sessions(id) ON DELETE SET NULL,
    last_checked_at TIMESTAMP WITH TIME ZONE,
    raw_status JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_v2_channel_live_states_status
        CHECK (status IN ('OPEN', 'CLOSE', 'UNKNOWN'))
);

CREATE INDEX IF NOT EXISTS idx_v2_channel_live_states_current_stream_session_id
ON v2_channel_live_states(current_stream_session_id);

DROP TRIGGER IF EXISTS trg_v2_channel_live_states_updated_at ON v2_channel_live_states;
CREATE TRIGGER trg_v2_channel_live_states_updated_at
BEFORE UPDATE ON v2_channel_live_states
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_live_notifications (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_id UUID NOT NULL REFERENCES v2_channels(id) ON DELETE CASCADE,
    destination_platform VARCHAR(50) NOT NULL,
    destination_channel_id VARCHAR(255) NOT NULL,
    mention_role VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_v2_live_notifications_destination
        UNIQUE (channel_id, destination_platform, destination_channel_id)
);

DROP TRIGGER IF EXISTS trg_v2_live_notifications_updated_at ON v2_live_notifications;
CREATE TRIGGER trg_v2_live_notifications_updated_at
BEFORE UPDATE ON v2_live_notifications
FOR EACH ROW
EXECUTE FUNCTION v2_set_updated_at();

CREATE TABLE IF NOT EXISTS v2_live_notification_deliveries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notification_id BIGINT NOT NULL REFERENCES v2_live_notifications(id) ON DELETE CASCADE,
    stream_session_id UUID NOT NULL REFERENCES v2_stream_sessions(id) ON DELETE CASCADE,
    delivered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message TEXT,

    CONSTRAINT unique_v2_live_notification_delivery
        UNIQUE (notification_id, stream_session_id),
    CONSTRAINT chk_v2_live_notification_deliveries_status
        CHECK (delivery_status IN ('pending', 'success', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_v2_live_notification_deliveries_stream_session_id
ON v2_live_notification_deliveries(stream_session_id);
