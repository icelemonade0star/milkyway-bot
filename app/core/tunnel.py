from sshtunnel import SSHTunnelForwarder
import app.core.config as config

class ParamikoTunnel:
    _instance = None
    _server = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            if config.SSH_HOST:
                cls._instance.init_tunnel()
            else:
                print("⚠️ SSH_HOST 설정이 없어 터널링을 생략합니다.")
        return cls._instance

    def init_tunnel(self):
        try:
            # 리모트 DB 설정
            remote_db_host = config.DB_HOST or "127.0.0.1"
            remote_db_port = int(config.DB_PORT)

            # 터널 서버 설정
            self._server = SSHTunnelForwarder(
                (config.SSH_HOST, config.SSH_PORT),
                ssh_username=config.SSH_USER,
                ssh_password=config.SSH_PASSWORD,
                ssh_pkey=config.SSH_PRIVATE_KEY_PATH,
                remote_bind_address=(remote_db_host, remote_db_port),
                local_bind_address=('127.0.0.1', 0) # 로컬의 남는 포트에 바인딩
            )
            
            self._server.start()
            print(f"✅ SSH 터널 시작됨 - 로컬 포트: {self._server.local_bind_port}")
            
        except Exception as e:
            print(f"❌ SSH 터널 실패: {e}")

    @property
    def local_port(self):
        return self._server.local_bind_port if self._server else 5432

    def stop(self):
        if self._server:
            self._server.stop()
            print("🔒 SSH 터널 종료")