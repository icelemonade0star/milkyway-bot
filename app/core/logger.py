import logging
import os
import sys

# 공통 로그 포맷 정의
LOG_FORMAT = "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s"

def setup_global_logging():
    """앱 전역 로깅 설정 (Main 진입점에서 호출 권장)"""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def get_logger(name: str):
    """일반 모듈용 표준 로거"""
    return logging.getLogger(name)

def get_channel_logger(channel_name: str):
    """
    채팅 클라이언트 전용 로거 (기존 ChatClient 내부 로직 이동)
    - logs/{channel_name}/chat_client.log 에 파일로 저장
    - 콘솔 중복 출력을 막기 위해 propagate=False 설정
    """
    logger = logging.getLogger(f"Chzzk.{channel_name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False 

    # 로그 디렉토리 생성 (OS 호환 경로)
    log_dir = os.path.join("logs", channel_name)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "chat_client.log")
    
    # 중복 핸들러 추가 방지
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(LOG_FORMAT)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
