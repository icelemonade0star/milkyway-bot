from flask import Flask, render_template_string, request
import re
import requests

app = Flask(__name__)

# ==========================================
# 🛠️ 백엔드: 링크 파싱 및 데이터 추출 로직 (video_test.py 기반)
# ==========================================

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
            "message": f"유튜브 영상 로드 성공 (ID: {video_id})"
        }
    return {"error": "유효하지 않은 유튜브 링크입니다."}

def parse_chzzk_clip(url):
    """치지직 클립 링크에서 ID와 길이, 메타데이터를 추출합니다."""
    print(f"\n[Backend] 치지직 클립 파싱 시도: {url}")
    match = re.search(r"clips/([a-zA-Z0-9_-]+)", url)
    if not match:
        print("[Backend] 에러: 링크에서 클립 ID를 찾을 수 없습니다.")
        return {"error": "유효하지 않은 치지직 클립 링크입니다."}
    
    clip_id = match.group(1)
    api_url = f"https://api.chzzk.naver.com/service/v1/clips/{clip_id}/detail"
    params = {"optionalProperties": "MAKER_CHANNEL"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    print(f"[Backend] 치지직 API 호출 중: {api_url}")
    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=5)
        print(f"[Backend] 치지직 API 응답 코드: {response.status_code}")
        if response.status_code == 200:
            data = response.json().get("content", {})
            
            duration = data.get("duration", 0)
            title = data.get("clipTitle", "제목 없음")
            maker_channel = data.get("optionalProperty", {}).get("makerChannel", {})
            channel_name = maker_channel.get("channelName", "알 수 없는 채널")
            
            print(f"[Backend] 치지직 파싱 성공: {title} ({duration}초)")
            return {
                "platform": "CHZZK_CLIP",
                "clip_id": clip_id,
                "duration": duration,
                "title": title,
                "channel_name": channel_name,
                "url": url,
                "message": f"치지직 클립 로드 성공: '{title}' ({duration}초)"
            }
        else:
            print(f"[Backend] 에러: API 응답 실패. 내용: {response.text}")
            return {"error": f"치지직 API 호출 실패 (상태 코드: {response.status_code})"}
            
    except Exception as e:
        print(f"[Backend] 에러: 예외 발생 - {e}")
        return {"error": f"치지직 클립 정보 처리 중 에러 발생: {e}"}

def process_url(url):
    """입력된 URL에 맞춰 유튜브와 치지직을 라우팅합니다."""
    if not url:
        return None
        
    url_match = re.search(r"(https?://[^\s]+)", url)
    if not url_match:
        return {"error": "입력값에 유효한 링크가 포함되어 있지 않습니다."}
        
    extracted_url = url_match.group(1)
    
    if "youtube.com" in extracted_url or "youtu.be" in extracted_url:
        return parse_youtube(extracted_url)
    elif "chzzk.naver.com/clips/" in extracted_url:
        return parse_chzzk_clip(extracted_url)
    else:
        return {"error": "지원하지 않는 플랫폼의 링크입니다. (현재 유튜브, 치지직 클립만 지원)"}

# ==========================================
# 🌐 프론트엔드: HTML & JavaScript 템플릿
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>Milkyway Bot - 서드파티 미디어 테스트</title>
    <style>
        body { font-family: 'Malgun Gothic', sans-serif; background-color: #f4f6f9; padding: 20px; text-align: center; color: #333; }
        h1 { margin-bottom: 10px; }
        .controls { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); display: inline-block; margin-bottom: 20px; width: 600px; }
        input[type="text"] { padding: 12px; width: 420px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
        button { padding: 12px 20px; background-color: #00d169; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px; transition: 0.2s; }
        button:hover { background-color: #00b359; }
        
        .result-box { background: #1e1e1e; color: #00ff66; text-align: left; padding: 15px; border-radius: 8px; width: 600px; margin: 0 auto 20px auto; overflow-x: auto; font-family: 'Consolas', monospace; box-shadow: inset 0 0 10px rgba(0,0,0,0.5); }
        .error-box { background: #ffe6e6; color: #ff3333; text-align: left; padding: 15px; border-radius: 8px; width: 600px; margin: 0 auto 20px auto; border: 1px solid #ff3333; font-weight: bold; }
        
        #player-container { display: flex; justify-content: center; }
        .player-wrapper { border: 4px solid #333; box-shadow: 0 4px 15px rgba(0,0,0,0.3); background: #000; width: 640px; height: 360px; border-radius: 4px; overflow: hidden; }
        #debug-log { background: #fff; padding: 15px; border-radius: 8px; width: 600px; margin: 20px auto; text-align: left; font-size: 13px; color: #555; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: 1px solid #ccc; }
    </style>
    <script>
        function addLog(msg) {
            const logBox = document.getElementById('log-content');
            if (logBox) logBox.innerHTML += `<div>[${new Date().toLocaleTimeString()}] ${msg}</div>`;
            console.log(`[Frontend Log] ${msg}`);
        }
    </script>
</head>
<body>
    <h1>🎬 미디어 서드파티 연동 테스트 페이지</h1>
    <p style="color: #666; margin-bottom: 30px;">치지직 클립 및 유튜브 링크를 입력하면 정보를 파싱하고 영상을 재생합니다.</p>
    
    <div class="controls">
        <form action="/" method="get">
            <input type="text" name="url" placeholder="유튜브 링크 또는 치지직 클립 링크 입력" value="{{ input_url }}">
            <button type="submit">영상 불러오기</button>
        </form>
    </div>

    {% if result %}
        {% if result.error %}
            <div class="error-box">
                ⚠️ 오류 발생: {{ result.error }}
            </div>
        {% else %}
            <!-- 파싱된 데이터 출력 -->
            <div class="result-box">
                <strong style="color: #fff;">[서버 파싱 결과]</strong>
                <pre>{{ result | tojson(indent=2) }}</pre>
            </div>

            <!-- 영상 플레이어 -->
            <div id="player-container">
                {% if result.platform == 'YOUTUBE' %}
                    <div class="player-wrapper">
                        <div id="youtube-player"></div>
                    </div>
                    <script>
                        var tag = document.createElement('script');
                        tag.src = "https://www.youtube.com/iframe_api";
                        var firstScriptTag = document.getElementsByTagName('script')[0];
                        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

                        var player;
                        function onYouTubeIframeAPIReady() {
                            player = new YT.Player('youtube-player', {
                                height: '100%',
                                width: '100%',
                                videoId: '{{ result.video_id }}',
                                playerVars: { 'autoplay': 1, 'playsinline': 1, 'controls': 1 }
                            });
                        }
                    </script>
                {% elif result.platform == 'CHZZK_CLIP' %}
                    <div class="player-wrapper">
                        <iframe 
                            id="chzzk-player"
                            src="https://chzzk.naver.com/embed/clip/{{ result.clip_id }}" 
                            width="100%" 
                            height="100%" 
                            frameborder="0" 
                            title="CHZZK Player"
                            allow="autoplay; clipboard-write; web-share; fullscreen; encrypted-media" 
                            onload="addLog('✅ 치지직 iframe 문서 로드 완료 (내부 영상 재생 여부와는 다를 수 있음)')"
                            allowfullscreen>
                        </iframe>
                    </div>
                    <script>
                        addLog("⏳ 치지직 클립 iframe 렌더링 시작 (Clip ID: {{ result.clip_id }})");
                    </script>
                {% endif %}
            </div>

            <!-- 프론트엔드 디버그 로그 UI -->
            <div id="debug-log">
                <strong style="color: #333;">🖥️ 프론트엔드 진행 로그</strong>
                <div id="log-content" style="margin-top: 10px; font-family: 'Consolas', monospace; color: #d10000;"></div>
            </div>
        {% endif %}
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    input_url = request.args.get('url', '')
    result = process_url(input_url) if input_url else None
    return render_template_string(HTML_TEMPLATE, input_url=input_url, result=result)

if __name__ == '__main__':
    print("==================================================")
    print(" 🎬 밀키웨이 봇 미디어 통합 테스트 서버가 시작되었습니다.")
    print(" 👉 브라우저에서 http://localhost:5000 에 접속하세요.")
    print("==================================================")
    app.run(port=5000, debug=True)
