milkyway-bot/
  app/
    main.py          # FastAPI 엔트리
    deps.py          # 의존성 주입 (세션, 클라이언트 등)
    api/
      routes_chat.py # HTTP/WebSocket 엔드포인트
    bot/
      __init__.py
      core.py        # 봇 로직 (명령어, 핸들러)
      commands.py
      events.py
    chzzk/
      __init__.py
      client.py      # chzzk REST/Session 클라이언트
      models.py
    config.py        # 설정 (ENV 로드)
  tests/
  pyproject.toml or requirements.txt
  .env.example
  README.md