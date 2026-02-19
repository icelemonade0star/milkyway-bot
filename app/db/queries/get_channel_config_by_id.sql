SELECT 
    command_prefix 
FROM channel_config 
WHERE channel_id = (:channel_id)::text
AND is_active = true;