SELECT 
    channel_id, 
    channel_name, 
    expires_at, 
    created_at 
FROM auth_token
WHERE (:channel_name::text IS NULL OR channel_name LIKE :channel_name_like::text)
ORDER BY created_at DESC;