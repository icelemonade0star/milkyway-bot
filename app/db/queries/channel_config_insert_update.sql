UPDATE channel_config
SET 
    command_prefix = (:command_prefix)::text, 
    language = (:language)::text,
    is_active = (:is_active)::boolean
WHERE channel_id = (:channel_id)::text;