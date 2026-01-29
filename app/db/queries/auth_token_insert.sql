INSERT INTO auth_token (
    channel_id, channel_name, access_token, refresh_token, expires_at
) VALUES (
    :channel_id,
    :channel_name,
    :access_token,
    :refresh_token,
    CURRENT_TIMESTAMP + INTERVAL '24 hours'
)
RETURNING channel_id, channel_name, expires_at;