import os
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder

load_dotenv()

class SshTunnelManager:
    _instance = None
    _server = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init_tunnel()
        return cls._instance
    
    def init_tunnel(self):
        self._server = SSHTunnelForwarder(
            (os.getenv("SSH_HOST"), int(os.getenv("SSH_PORT"))),
            ssh_username=os.getenv("SSH_USER"),
            ssh_password=os.getenv("SSH_PASSWORD"),
            remote_bind_address=(os.getenv("DB_HOST"), int(os.getenv("DB_PORT")))
        )
        self._server.start()
        print(f"✅ SSH 터널 시작됨 - 포트: {self._server.local_bind_port}")
    
    @property
    def local_port(self):
        return self._server.local_bind_port
    
    def stop(self):
        if self._server:
            self._server.stop()
            print("🔒 SSH 터널 종료")

# FastAPI 시작시 한 번만 실행
tunnel = SshTunnelManager()