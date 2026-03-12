from playwright.async_api import async_playwright
import asyncio
import os
import json

class ChzzkCookieGetter:
    def __init__(self):
        self.NID_AUT = None
        self.NID_SES = None
    
    async def login_and_get_cookies(self, chzzk_id: str, chzzk_pw: str):
        async with async_playwright() as p:
            # 서버 환경(Docker 등)에서는 headless=True가 필수적입니다.
            # --no-sandbox, --disable-dev-shm-usage는 컨테이너 환경에서 크래시 방지를 위해 권장됩니다.
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            
            # 네이버 보안 우회를 위해 user_agent 설정 및 뷰포트 설정
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = await context.new_page()
            
            # 1. 네이버 로그인 페이지로 이동
            await page.goto("https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fchzzk.naver.com%2F")
            
            # 2. ID/PW 입력 (page.fill 대신 JS 주입 사용 - 봇 탐지 우회)
            # 네이버는 타이핑 속도를 감지하므로 element.value에 직접 값을 넣습니다.
            await page.evaluate(f"document.getElementById('id').value = '{chzzk_id}'")
            await page.evaluate(f"document.getElementById('pw').value = '{chzzk_pw}'")
            
            # 3. 로그인 버튼 클릭 (캡차 있을 수 있음)
            await page.click(".btn_login")
            
            # 4. 로그인 성공 대기 (URL이 치지직으로 변경될 때까지 대기)
            try:
                print("로그인 처리 중...")
                await page.wait_for_url("https://chzzk.naver.com/**", timeout=60000)
            except Exception:
                print("❌ 로그인 시간 초과 또는 실패. 스크린샷을 확인하세요.")
                
            
            # 5. 쿠키 추출
            cookies = await context.cookies()
            naver_cookies = {c['name']: c['value'] for c in cookies 
                           if c['domain'].endswith('naver.com')}
            
            self.NID_AUT = naver_cookies.get('NID_AUT')
            self.NID_SES = naver_cookies.get('NID_SES')
            
            await browser.close()
            return self.NID_AUT, self.NID_SES

# 사용법
if __name__ == "__main__":
    async def main():
        getter = ChzzkCookieGetter()
        # 실제 계정 정보로 테스트 필요
        nid_aut, nid_ses = await getter.login_and_get_cookies(
            "YOUR_ID", "YOUR_PW"
        )
        if nid_aut and nid_ses:
            print(f"✅ 쿠키 추출 성공!")
            print(f"NID_AUT: {nid_aut}")
            print(f"NID_SES: {nid_ses}")
            
            # 쿠키를 파일로 저장
            with open("chzzk_cookies.json", "w") as f:
                json.dump({"NID_AUT": nid_aut, "NID_SES": nid_ses}, f)
        else:
            print("❌ 쿠키 추출 실패")

    asyncio.run(main())
