import re
import requests
import json

def parse_youtube(url):
    """유튜브 링크에서 Video ID를 추출합니다."""
    regex = r"(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^\"&?\/\s]{11})"
    match = re.search(regex, url)
    
    if match:
        video_id = match.group(1)
        return {
            "platform": "YOUTUBE",
            "video_id": video_id,
            "url": url,
            "message": f"유튜브 영상이 대기열에 추가되었습니다. (ID: {video_id})"
        }
    return {"error": "유효하지 않은 유튜브 링크입니다."}


def parse_chzzk_clip(url):
    """치지직 클립 링크에서 ID와 길이(Duration)를 추출합니다."""
    match = re.search(r"clips/([a-zA-Z0-9_-]+)", url)
    if not match:
        return {"error": "유효하지 않은 치지직 클립 링크입니다."}
    
    clip_id = match.group(1)
    api_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    
    params = {"optionalProperties": "MAKER_CHANNEL"}
    
    try:
        response = requests.get(api_url, params=params)
        if response.status_code == 200:
            data = response.json().get("content", {})
            
            # 핵심 데이터 추출
            duration = data.get("duration", 0)
            title = data.get("clipTitle", "제목 없음")
            
            # 채널 이름 안전하게 추출 (makerChannel이 없을 수도 있으니 get으로 방어)
            maker_channel = data.get("optionalProperty", {}).get("makerChannel", {})
            channel_name = maker_channel.get("channelName", "알 수 없는 채널")
            
            return {
                "platform": "CHZZK_CLIP",
                "clip_id": clip_id,
                "duration": duration,  # 오버레이 강제 폭파 타이머용!
                "title": title,
                "channel_name": channel_name,
                "url": url,
                "message": f"치지직 클립 '{title}' ({duration}초) 대기열 추가 완료!"
            }
        else:
            return {"error": f"치지직 API 호출 실패 (상태 코드: {response.status_code})"}
            
    except Exception as e:
        return {"error": f"치지직 클립 정보 처리 중 에러 발생: {e}"}


def process_chat_message(chat_text):
    """채팅 메시지를 분석하여 링크 플랫폼에 맞게 분기 처리합니다."""
    
    # 1. 채팅창 메시지에서 'http' 또는 'https'로 시작하는 링크만 쏙 뽑아냅니다.
    url_match = re.search(r"(https?://[^\s]+)", chat_text)
    
    if not url_match:
        return {"error": "메시지에 링크가 포함되어 있지 않습니다."}
        
    url = url_match.group(1)
    
    # 2. 플랫폼 분기 처리 (라우팅)
    if "youtube.com" in url or "youtu.be" in url:
        return parse_youtube(url)
        
    elif "chzzk.naver.com/clips/" in url:
        return parse_chzzk_clip(url)
        
    else:
        return {"error": "지원하지 않는 플랫폼의 링크입니다. (현재 유튜브, 치지직 클립만 지원)"}

# ==========================================
# 🧪 테스트 실행 구역
# ==========================================
if __name__ == "__main__":
    # 시청자들이 채팅창에 입력했다고 가정한 테스트 메시지들
    test_messages = [
        "!영상 https://youtu.be/dQw4w9WgXcQ 이거 틀어주세요!",
        "방장 이 치지직 클립 봐봐 ㅋㅋㅋ https://chzzk.naver.com/clips/KstVWY2qLX",
        "!영도 https://twitch.tv/clip/SomeRandomClip", # 지원 안 하는 링크 테스트
        "!영상 링크없는그냥채팅" # 링크 없는 채팅 테스트
    ]

    print("=== 밀키웨이 봇 영상 대기열 처리 테스트 ===\n")
    
    for msg in test_messages:
        print(f"📩 수신된 채팅: {msg}")
        result = process_chat_message(msg)
        
        # 결과를 보기 좋게 JSON 형태로 출력
        print(f"📤 처리 결과: {json.dumps(result, indent=2, ensure_ascii=False)}\n")