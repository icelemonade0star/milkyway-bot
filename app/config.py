# config.py
import os
from dotenv import load_dotenv

load_dotenv()

OPENAPI_BASE = "https://openapi.chzzk.naver.com"

# 치지직 API 토큰 정보
CLIENT_ID = '9ebe5989-29c5-4ab5-a4bc-19071b95245a'
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URL = 'https://milkywaybot.cloud/auth/callback'

# --- 데이터베이스 설정 ---
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

# --- SSH 터널링 설정 ---
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", "22"))
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
SSH_PRIVATE_KEY_PATH = os.getenv("SSH_PRIVATE_KEY_PATH")

# --- Redis 설정 ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))