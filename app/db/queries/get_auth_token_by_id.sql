SELECT 
    channel_id, 
    channel_name, 
    expires_at, 
    access_token 
FROM auth_token
WHERE channel_id = (:channel_id)::text;