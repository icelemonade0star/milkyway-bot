INSERT INTO auth_token (
    channel_id, 
    channel_name, 
    access_token, 
    refresh_token, 
    expires_at
) VALUES (
    (:channel_id)::text,
    (:channel_name)::text,
    (:access_token)::text,
    (:refresh_token)::text,
    CURRENT_TIMESTAMP + INTERVAL '24 hours'
)
ON CONFLICT (channel_id) DO UPDATE SET
    channel_name = EXCLUDED.channel_name,
    access_token = EXCLUDED.access_token,
    refresh_token = EXCLUDED.refresh_token,
    expires_at = EXCLUDED.expires_at,
    updated_at = CURRENT_TIMESTAMP
RETURNING channel_id, channel_name, expires_at;