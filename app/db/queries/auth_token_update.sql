UPDATE auth_token
SET 
    access_token = (:access_token)::text,
    refresh_token = COALESCE((:refresh_token)::text, refresh_token),
    expires_at = (:expires_at)::timestamp,
    updated_at = CURRENT_TIMESTAMP
WHERE channel_id = (:channel_id)::text;