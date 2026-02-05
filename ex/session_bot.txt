import asyncio
from chzzkpy import Client, Donation, Message, UserPermission

async def run_full_bot(client_id: str, client_secret: str):
    # 1. Client 초기화 (OAuth2)
    client = Client(client_id, client_secret)
    
    # 2. 이벤트 핸들러 먼저 정의
    @client.event
    async def on_chat(message: Message):
        print(f"[{message.profile.nickname}] {message.content}")
        if "안녕" in message.content:
            await message.send(f"{message.profile.nickname}님, 반갑습니다!")
    
    # 3. 인증 URL 출력
    auth_url = client.generate_authorization_token_url(
        redirect_url="http://localhost:8080/callback",
        state="state123"
    )
    print(f"🔗 인증 URL: {auth_url}")
    
    # 4. 인증 코드 입력
    code = input("브라우저 인증 후 코드를 입력하세요: ")
    
    # 5. UserClient 생성 & 연결
    user_client = await client.generate_user_client(code, "state123")
    await user_client.connect(UserPermission.all())
    
    print("✅ 봇 연결 완료! Ctrl+C로 종료")
    
    # 6. 무한 실행
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        await user_client.disconnect()
        await client.close()

if __name__ == "__main__":
    asyncio.run(run_full_bot(
        client_id="YOUR_CLIENT_ID",      # 치지직 개발자센터 발급
        client_secret="YOUR_CLIENT_SECRET"
    ))