import requests
import asyncio
import websockets
import json

# ==========================================
# 설정 변수
# ==========================================
USER_ID = "kkeuteopneun_hosu"  # 테스트할 스트리머/채널 ID
API_URL = f"https://ci.me/api/app/channels/{USER_ID}/chat-token"
WS_URL = "wss://edge.ivschat.ap-northeast-2.amazonaws.com/"

# ==========================================
# 1. API로 채팅방 입장 토큰 발급
# ==========================================
def get_chat_token():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        # 로그인 필요 시 아래 쿠키 주석 해제 후 값 입력
        # "Cookie": "mauth-authorization-code=..." 
    }

    print(f"🔄 [Step 1] 토큰 발급 요청 중... ({USER_ID})")
    try:
        response = requests.post(API_URL, headers=headers, timeout=10)
        response.raise_for_status() # 200 OK가 아니면 에러 발생
        
        json_data = response.json()
        
        # 응답 구조 변경: root -> data -> token
        token = json_data.get("data", {}).get("token")
        
        if not token:
            print(f"❌ 토큰을 찾을 수 없습니다. 응답 내용:\n{json.dumps(json_data, indent=2, ensure_ascii=False)}")
            return None
            
        print(f"✅ 토큰 발급 성공 (길이: {len(token)})")
        return token

    except Exception as e:
        print(f"❌ API 요청 실패: {e}")
        return None

# ==========================================
# 2. AWS IVS 웹소켓 연결
# ==========================================
async def connect_chat(token):
    print(f"\n🔄 [Step 2] 웹소켓 연결 시도: {WS_URL}")
    
    try:
        # AWS IVS는 발급받은 토큰을 subprotocols로 전달해야 합니다.
        async with websockets.connect(WS_URL, subprotocols=[token]) as ws:
            print("✅ 씨미 채팅 서버 연결 성공! (Ctrl+C로 종료)")
            
            while True:
                try:
                    message = await ws.recv()
                    try:
                        data = json.loads(message)
                        
                        # 채팅 메시지 타입인지 확인
                        if data.get("Type") == "MESSAGE":
                            content = data.get("Content", "")
                            sender = data.get("Sender", {})
                            user_id = sender.get("UserId", "Unknown")
                            
                            # 닉네임 정보는 Sender -> Attributes -> user (JSON 문자열) 안에 있음
                            user_attr_raw = sender.get("Attributes", {}).get("user", "{}")
                            try:
                                user_info = json.loads(user_attr_raw)
                                nickname = user_info.get("ch", {}).get("na", "Unknown")
                            except:
                                nickname = "Unknown"

                            print(f"💬 [{nickname}] ({user_id}): {content}")
                        
                    except json.JSONDecodeError:
                        pass
                        
                except websockets.exceptions.ConnectionClosed:
                    print("⚠️ 서버와의 연결이 끊어졌습니다.")
                    break
    except Exception as e:
        print(f"❌ 웹소켓 연결 에러: {e}")

async def main():
    token = get_chat_token()
    if token:
        await connect_chat(token)
    else:
        print("⛔ 토큰이 없어 연결을 종료합니다.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 테스트 종료")