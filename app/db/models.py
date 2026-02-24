from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

# database.py에 Base가 정의되어 있다면 그것을 import해서 써야 합니다.
# 여기서는 예시를 위해 새로 정의합니다.
Base = declarative_base()

class AuthToken(Base):
    __tablename__ = "auth_token"

    channel_id = Column(String(100), primary_key=True, comment="채널 고유 ID")
    channel_name = Column(String(50), nullable=False, comment="채널명")
    access_token = Column(Text, nullable=False, comment="액세스 토큰")
    refresh_token = Column(Text, nullable=False, comment="리프레시 토큰")
    expires_at = Column(DateTime(timezone=True), nullable=False, comment="만료 시간")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="생성일")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="수정일")

class ChannelConfig(Base):
    __tablename__ = "channel_config"

    # auth_token 테이블과 1:1 관계 (FK 설정)
    channel_id = Column(String(100), ForeignKey("auth_token.channel_id", ondelete="CASCADE"), primary_key=True, comment="채널 고유 ID")
    command_prefix = Column(String(10), default="!", nullable=False, comment="명령어 접두사")
    is_active = Column(Boolean, default=True, comment="채널 활성화 여부")
    language = Column(String(10), default="ko", comment="언어 설정")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class GlobalCommand(Base):
    __tablename__ = "global_chat_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    command = Column(String(100), unique=True, nullable=False, comment="명령어")
    response = Column(Text, nullable=True, comment="응답 메시지") # 기능형일 경우 비워둘 수 있음
    type = Column(String(20), default='text', nullable=False, comment="명령어 타입")
    cooldown_seconds = Column(Integer, default=5, nullable=False, comment="쿨타임")
    is_active = Column(Boolean, default=True, nullable=False, comment="활성화 여부")
    display_order = Column(Integer, default=0, nullable=False, comment="표시 순서")
    description = Column(String, nullable=True, comment="설명")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ChatCommand(Base):
    __tablename__ = "chat_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # auth_token 테이블의 channel_id와 외래키 연결 (테이블명 변경 반영)
    channel_id = Column(String(100), ForeignKey("auth_token.channel_id", ondelete="CASCADE"), nullable=False, comment="채널 ID")
    command = Column(String, nullable=False, comment="명령어")
    response = Column(Text, nullable=False, comment="응답 내용")
    type = Column(String, default="text", nullable=False, comment="응답 타입")
    is_active = Column(Boolean, default=True, nullable=False, comment="활성화 여부")
    cooldown_seconds = Column(Integer, default=5, nullable=False, comment="쿨타임(초)")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('channel_id', 'command', name='unique_command_per_channel'),
    )

class ChatGreeting(Base):
    __tablename__ = "chat_greetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(100), ForeignKey("auth_token.channel_id", ondelete="CASCADE"), nullable=False, comment="채널 ID")
    keyword = Column(String(100), nullable=False, comment="감지할 단어")
    response = Column(Text, nullable=False, comment="응답 내용")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('channel_id', 'keyword', name='unique_greeting_per_channel'),
    )