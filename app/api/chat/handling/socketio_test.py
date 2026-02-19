import socketio
import json


# 소켓 클라이언트 생성
sio = socketio.AsyncClient(
    request_timeout=10
)
session_key = None

class SocketState:
    session_key = None

state = SocketState()

def get_session_key():
    return state.session_key

# 연결 성공 이벤트 핸들러
@sio.event
async def connect():
    print("서버에 연결되었습니다.")

# 연결 에러 이벤트 핸들러
@sio.event
async def connect_error(data):
    print("서버에 연결 실패.")

# 연결 종료 이벤트 핸들러
@sio.event
async def disconnect():
    state.session_key = None  # 연결 종료 시 세션 키 초기화
    print("서버와 연결이 끊어졌습니다.")

# 치지직 서버에서 오는 이벤트 처리
@sio.on('SYSTEM')
async def on_system(data):
    print(f"📡 [DEBUG] SYSTEM 이벤트 원본 수신: {data}")
    data = json.loads(data)
    try:
        print("SYSTEM 이벤트 수신: %s", data)
        # data 내부에 sessionKey 등 연결 완료 정보가 포함됨

        event_type = data.get("type")
        event_data = data.get("data", {})
        
        if event_type == "connected":
            # 세션 키 저장
            state.session_key = event_data.get("sessionKey")
            print(f"세션 키 저장: {state.session_key}")

        elif event_type == "subscribed":
            event_type2 = event_data.get("eventType")
            channel_id = event_data.get("channelId")
            print(f"구독 완료 - eventType={event_type2}, channelId={channel_id}")

        else:
            # 예외처리
            print(f"알 수 없는 SYSTEM type: {event_type}")
    except Exception as e:
        print(f"❌ SYSTEM 이벤트 처리 중 에러: {e}")

# 치지직 서버에서 오는 채팅 이벤트 처리
@sio.on('CHAT')
async def on_chat(data):
    data = json.loads(data)
    print(f"CHAT 이벤트 수신: {data}")
    
    try:
        message = data.get('content')
        nickname = data.get('profile', {}).get('nickname')
        channelId = data.get('channelId')

        if message and nickname:
            print(f"[{nickname}] {message}")
    except Exception as e:
        print(f"CHAT 파싱 에러: {e}")

# 치지직 서버에서 오는 채팅 도네이션 처리
@sio.on('DONATION')
async def on_donation(data):
    data = json.loads(data)
    print(f"DONATION - type={data.get('donationType')}, nickname={data.get('donatorNickname')}, amount={data.get('payAmount')}, text={data.get('donationText')}")