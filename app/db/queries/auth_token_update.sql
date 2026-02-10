UPDATE auth_token
SET 
    access_token = (:access_token)::text,
    refresh_token = (:refresh_token)::text,
    expires_at = (:expires_at)::timestamp,
    updated_at = CURRENT_TIMESTAMP
WHERE channel_id = (:channel_id)::text;