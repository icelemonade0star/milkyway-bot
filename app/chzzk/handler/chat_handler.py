from app.chzzk.base_socket_client import BaseSocketEventHandler

class ChatHandler(BaseSocketEventHandler):
    async def handle_event(self, event_type: str, data: dict) -> None:
        channel_id = data.get("channelId")
        nickname = data.get("senderNickname")
        content = data.get("content")
        print(f"💬 [{channel_id}] {nickname}: {content}")