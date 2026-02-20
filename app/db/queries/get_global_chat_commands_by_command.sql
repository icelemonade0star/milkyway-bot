SELECT 
    response,
    type
FROM global_chat_commands 
WHERE command = (:command)::text
AND is_active = true;