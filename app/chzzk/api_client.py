# api_client.py
import requests

from config import OPENAPI_BASE

class ChzzkAPIClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = f"{OPENAPI_BASE}/open/v1"
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def create_session_url(self) -> str:
        resp = requests.get(
            f"{self.base_url}/sessions/auth", 
            headers=self.headers
        )
        resp.raise_for_status()
        return resp.json()["url"]
        
    def subscribe_chat(self, session_key: str, channel_id: str) -> None:
        params = {"sessionKey": session_key, "channelId": channel_id}
        resp = requests.post(
            f"{self.base_url}/sessions/events/subscribe/chat",
            headers=self.headers,
            params=params
        )
        resp.raise_for_status()
        print("Subscribed:", resp.text)