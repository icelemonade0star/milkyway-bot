from app.chzzk.base_socket_client import BaseSocketEventHandler

class DonationHandler(BaseSocketEventHandler):
    async def handle_event(self, event_type: str, data: dict) -> None:
        sender = data.get("senderNickname")
        amount = data.get("amount", "N/A")
        message = data.get("message", "")
        print(f"🎁 후원: {sender} ({amount}) - {message}")