import socketio
import session as m_session

def connect_session(socket_url: str):
    sio = socketio.Client()

    session_key = {"value": None}

    @sio.event
    def connect():
        print("connected to session server")

    @sio.on("message")
    def on_message(data):
        print("raw message:", data)
        # 시스템 메시지 형식: { "type": "connected", "data": { "sessionKey": "..." } }
        if isinstance(data, dict) and data.get("type") == "connected":
            session_key["value"] = data["data"]["sessionKey"]
            print("sessionKey:", session_key["value"])

    @sio.event
    def disconnect():
        print("disconnected from session server")

    # chzzk에서 주는 url 은 https://ssioXX.nchat.naver.com:443?auth=... 형태.[web:7][web:9]
    # python-socketio 가 자동으로 websocket으로 붙을 수 있게 변형 없이 넘겨도 동작하는 경우가 많다.
    sio.connect(socket_url, transports=["websocket"])
    return sio, session_key


def run_simple_chat_listener(channel_id: str):
    socket_url = m_session.create_session_url()
    sio, session_key = connect_session(socket_url)

    # sessionKey가 들어올 때까지 잠깐 기다리는 단순 폴링 예시
    import time
    while session_key["value"] is None:
        time.sleep(0.1)

    m_session.subscribe_chat(session_key["value"], channel_id)

    @sio.on("message")
    def on_message(data):
        # SYSTEM, CHAT, DONATION, SUBSCRIPTION 등이 들어올 수 있음.[web:9]
        if not isinstance(data, dict):
            print("unknown message:", data)
            return

        event_type = data.get("eventType") or data.get("type")

        # 채팅 이벤트 (Event Type : CHAT)
        if event_type == "CHAT":
            # 공식 문서 기준 필드 예시: channelId, senderChannelId, senderNickname, content 등.[web:9]
            channel_id = data.get("channelId")
            nickname = data.get("senderNickname")
            content = data.get("content")
            print(f"[{channel_id}] {nickname}: {content}")

        # 시스템 메시지 (connected / subscribed / unsubscribed ...)
        elif event_type == "SYSTEM" or data.get("type") in ("connected", "subscribed", "unsubscribed"):
            print("system:", data)
        else:
            print("other event:", data)

    # 여기서는 단순히 블로킹으로 유지
    try:
        sio.wait()
    except KeyboardInterrupt:
        sio.disconnect()