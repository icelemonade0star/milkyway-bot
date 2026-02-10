import httpx
import websockets
import json
import asyncio

class ChatService:
    def __init__(self, access_token: str, channel_id: str):
        self.access_token = access_token
        self.channel_id = channel_id
        self.chat_url = "wss://kr-ss1.chat.naver.com/chat" # 또는 API로 받아온 주소

    async def get_chat_access_token(self):
        """치지직 채팅 서버 전용 토큰 발급"""
        url = f"https://openapi.chzzk.naver.com/open/v1/chats/access-token?channelId={self.channel_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers)
            return res.json()["content"]

    async def run_bot(self):
        # 1. 채팅용 임시 토큰과 서버 정보 가져오기
        auth_info = await self.get_chat_access_token()
        chat_token = auth_info["accessToken"]
        extra_token = auth_info.get("extraToken", "")

        async with websockets.connect(self.chat_url) as ws:
            # 2. 서버 연결 (Connect)
            connect_msg = {
                "ver": "2",
                "cmd": 100, # CONNECT
                "svcid": "game",
                "cid": auth_info["chatChannelId"],
                "tid": 1,
                "bdy": {
                    "accTkn": chat_token,
                    "auth": "SEND", # 발송 권한까지 포함
                    "devType": 2001
                }
            }
            await ws.send(json.dumps(connect_msg))

            # 3. 메시지 수신 루프
            print(f"✅ [{self.channel_id}] 봇 가동 시작!")
            while True:
                msg_raw = await ws.recv()
                data = json.loads(msg_raw)

                # 채팅 메시지 처리 (cmd: 9310)
                if data.get("cmd") == 9310:
                    for chat in data['bdy']:
                        msg_text = chat.get('msg', '')
                        nickname = json.loads(chat['profile']).get('nickname')
                        print(f"💬 [{nickname}]: {msg_text}")

                # Ping (연결 유지)
                if data.get("cmd") == 0:
                    await ws.send(json.dumps({"cmd": 10000}))