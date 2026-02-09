import os
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv

load_dotenv()

class ParamikoTunnel:
    _instance = None
    _server = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init_tunnel()
        return cls._instance

    def init_tunnel(self):
        try:
            # SSH 설정
            ssh_host = os.getenv("SSH_HOST")
            ssh_port = int(os.getenv("SSH_PORT", 22))
            ssh_user = os.getenv("SSH_USER")
            ssh_password = os.getenv("SSH_PASSWORD")
            ssh_key = os.getenv("SSH_PRIVATE_KEY_PATH")

            # 리모트 DB 설정
            remote_db_host = "127.0.0.1"
            remote_db_port = 5432

            # 터널 서버 설정
            self._server = SSHTunnelForwarder(
                (ssh_host, ssh_port),
                ssh_username=ssh_user,
                ssh_password=ssh_password,
                ssh_pkey=ssh_key,
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

tunnel = ParamikoTunnel()