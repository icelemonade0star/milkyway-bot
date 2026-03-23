from flask import Flask, render_template_string, request
import re

app = Flask(__name__)

# --- HTML/JS 템플릿 (프론트엔드) ---
# 유튜버 공식 IFrame API를 활용하여 플레이어를 구현합니다.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>Milkyway Bot - 유튜브 API 테스트</title>
    <style>
        body { font-family: sans-serif; background-color: #f0f0f0; padding: 20px; text-align: center; }
        h1 { color: #333; }
        .controls { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); display: inline-block; margin-bottom: 20px; }
        input[type="text"] { padding: 10px; width: 300px; border: 1px solid #ddd; border-radius: 4px; }
        button { padding: 10px 20px; background-color: #ff0000; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; }
        button:hover { background-color: #cc0000; }
        #player-container { margin-top: 20px; display: flex; justify-content: center; }
        /* OBS 오버레이처럼 보이게 하기 위한 스타일 */
        #player { border: 4px solid #333; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }
        .log { margin-top: 20px; color: #666; font-size: 0.9em; border-top: 1px solid #ccc; padding-top: 10px; width: 640px; margin-left: auto; margin-right: auto; text-align: left; }
    </style>
</head>
<body>
    <h1>📹 유튜브 API 재생 테스트</h1>
    
    <div class="controls">
        <form action="/" method="get">
            <input type="text" name="url" placeholder="유튜브 링크를 입력하세요 (예: https://youtu.be/...)" value="{{ youtube_url }}">
            <button type="submit">영상 재생</button>
        </form>
    </div>

    <div id="player-container">
        <div id="player"></div>
    </div>

    <div class="log">
        <strong>플레이어 상태 로그:</strong>
        <ul id="event-log"></ul>
    </div>

    <script>
      var tag = document.createElement('script');
      tag.src = "https://www.youtube.com/iframe_api";
      var firstScriptTag = document.getElementsByTagName('script')[0];
      firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

      var player;
      var videoId = '{{ video_id }}'; // 파이썬에서 넘겨받은 Video ID

      function appendLog(msg) {
          var logUl = document.getElementById('event-log');
          var li = document.createElement('li');
          li.innerText = new Date().toLocaleTimeString() + " - " + msg;
          logUl.appendChild(li);
          // 최신 로그가 보이도록 스크롤
          logUl.scrollTop = logUl.scrollHeight;
      }

      // 2. API 코드가 다운로드된 후 이 함수가 자동으로 호출되어 플레이어를 생성합니다.
      function onYouTubeIframeAPIReady() {
        if (!videoId) {
            appendLog("재생할 영상 ID가 없습니다. 링크를 입력해 주세요.");
            return;
        }

        appendLog("유튜브 API 로드 완료. 플레이어 생성 중... (Video ID: " + videoId + ")");
        
        player = new YT.Player('player', {
          height: '360',
          width: '640',
          videoId: videoId,
          playerVars: {
            'playsinline': 1,    // iOS 브라우저 등에서 전체화면 재생 방지
            'autoplay': 1,       // 자동 재생 시도
            'controls': 1,       // 컨트롤바 표시 (0으로 하면 오버레이처럼 보임)
            'rel': 0,            // 재생 종료 후 관련 영상 표시 안 함
            // 'mute': 1         // 💡 자동 재생 정책 확인을 위해 주석 처리해 둡니다.
          },
          events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange,
            'onError': onPlayerError
          }
        });
      }

      // 3. 플레이어가 준비되면 호출되는 함수
      function onPlayerReady(event) {
        appendLog("플레이어 준비 완료 (onReady). 재생 시도...");
        // API를 통해 재생 명령을 내립니다. 브라우저 정책에 따라 막힐 수 있습니다.
        event.target.playVideo();
      }

      // 4. 플레이어 상태가 변경될 때마다 호출되는 함수 (재생 중, 일시정지, 종료 등)
      function onPlayerStateChange(event) {
        var stateStr = "";
        switch (event.data) {
            case YT.PlayerState.UNSTARTED: stateStr = "시작되지 않음 (-1)"; break;
            case YT.PlayerState.ENDED:     stateStr = "종료됨 (0)"; break;
            case YT.PlayerState.PLAYING:   stateStr = "재생 중 (1)"; break;
            case YT.PlayerState.PAUSED:    stateStr = "일시정지 (2)"; break;
            case YT.PlayerState.BUFFERING: stateStr = "버퍼링 중 (3)"; break;
            case YT.PlayerState.CUED:      stateStr = "영상 신호 받음 (5)"; break;
        }
        appendLog("상태 변경: " + stateStr);
      }

      // 5. 에러 발생 시 호출되는 함수 (퍼가기 금지, 연령 제한 등)
      function onPlayerError(event) {
          var errorMsg = "알 수 없는 에러";
          switch (event.data) {
              case 2:   errorMsg = "잘못된 Video ID"; break;
              case 5:   errorMsg = "HTML5 플레이어 관련 에러"; break;
              case 100: errorMsg = "영상을 찾을 수 없거나 비공개 상태"; break;
              case 101: 
              case 150: errorMsg = "퍼가기가 허용되지 않은 영상 (저작권 등)"; break;
          }
          appendLog("⚠️ 에러 발생: " + errorMsg + " (Code: " + event.data + ")");
          alert("영상을 재생할 수 없습니다: " + errorMsg);
      }
    </script>
</body>
</html>
"""

# --- 백엔드 로직 (파이썬) ---

def extract_video_id(url):
    """유튜브 URL에서 Video ID를 추출하는 간단한 정규표현식 함수입니다."""
    if not url: return None
    regex = r"(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^\"&?\/\s]{11})"
    match = re.search(regex, url)
    return match.group(1) if match else None

@app.route('/', methods=['GET'])
def index():
    # GET 파라미터로 'url' 값을 받습니다. (예: /?url=https://...)
    youtube_url = request.args.get('url', '')
    video_id = extract_video_id(youtube_url)
    
    # HTML 템플릿에 데이터(URL, Video ID)를 채워서 브라우저에 보냅니다.
    return render_template_string(HTML_TEMPLATE, youtube_url=youtube_url, video_id=video_id)

if __name__ == '__main__':
    print("*" * 50)
    print("밀키웨이 봇 유튜브 API 테스트 서버가 시작되었습니다.")
    print("브라우저에서 http://localhost:5000 에 접속하세요.")
    print("*" * 50)
    # 서버 실행 (debug=True로 설정하면 코드 수정 시 자동으로 서버가 재시작됩니다.)
    app.run(port=5000, debug=True)