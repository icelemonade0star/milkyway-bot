INSERT INTO channel_config (
    channel_id, 
    command_prefix, 
    language
) VALUES (
    (:channel_id)::text,
    '!', 
    'ko'
)
ON CONFLICT (channel_id) DO NOTHING;