SELECT 
    channel_id, 
    channel_name, 
    expires_at, 
    access_token 
FROM auth_token
WHERE (:channel_name LIKE :channel_name_like)
ORDER BY expires_at DESC;