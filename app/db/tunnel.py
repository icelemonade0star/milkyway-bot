import os
from dotenv import load_dotenv
import paramiko
import threading
from contextlib import contextmanager

load_dotenv()

class ParamikoTunnel:
    _instance = None
    _transport = None
    _local_port = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init_tunnel()
        return cls._instance
    
    def init_tunnel(self):
        try:
            self._transport = paramiko.Transport(
                (os.getenv("SSH_HOST"), int(os.getenv("SSH_PORT")))
            )
            
            # 비밀번호 또는 키 인증
            if os.getenv("SSH_PASSWORD"):
                self._transport.connect(
                    username=os.getenv("SSH_USER"),
                    password=os.getenv("SSH_PASSWORD")
                )
            else:
                key = paramiko.RSAKey.from_private_key_file(
                    os.getenv("SSH_PRIVATE_KEY_PATH")
                )
                self._transport.connect(
                    username=os.getenv("SSH_USER"),
                    pkey=key
                )
            
            # 로컬 포트 포워딩 (동적 할당)
            self._local_port = self._transport.request_port_forward("", 0)
            print(f"✅ SSH 터널 시작됨 - 로컬 포트: {self._local_port}")
            
        except Exception as e:
            print(f"❌ SSH 터널 실패: {e}")
            self._local_port = 5432  # 기본 DB 포트 fallback
    
    @property
    def local_port(self):
        return self._local_port or 5432
    
    def stop(self):
        if self._transport:
            self._transport.close()
            print("🔒 SSH 터널 종료")

# 싱글톤 인스턴스
tunnel = ParamikoTunnel()