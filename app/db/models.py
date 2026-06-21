from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(100), ForeignKey("auth_token.channel_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(100), nullable=False, comment="시청자 고유 ID")
    user_name = Column(String(100), nullable=True, comment="시청자 닉네임")
    
    attendance_count = Column(Integer, default=1, nullable=False, comment="총 출석 횟수")
    last_attendance_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="최근 출석일")
    streak_count = Column(Integer, default=1, nullable=False, comment="연속 출석 횟수")

    __table_args__ = (
        # 특정 채널 내에서 유저당 하나의 레코드만 존재하도록 설정
        UniqueConstraint('channel_id', 'user_id', name='unique_user_per_channel_attendance'),
    )

class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chzzk_channel_id = Column(String(50), nullable=False, index=True, comment="치지직 채널 ID")
    opened_at = Column(DateTime(timezone=True), nullable=False, index=True, comment="방송 시작 시각")
    closed_at = Column(DateTime(timezone=True), nullable=True, comment="방송 종료 시각")
    stream_title = Column(String(200), nullable=True)

    def __repr__(self):
        return f"<StreamSession(channel={self.chzzk_channel_id}, opened={self.opened_at})>"

class ChzzkNotification(Base):
    __tablename__ = "chzzk_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chzzk_channel_id = Column(String(50), nullable=False, comment="치지직 채널 ID")
    discord_channel_id = Column(String(50), nullable=False, comment="디스코드 채널 ID")
    mention_role = Column(String(100), default='@everyone', comment="알림 시 멘션할 역할")
    streamer_name = Column(String(50), nullable=True, comment="스트리머 이름 (표시용)")
    is_active = Column(Boolean, default=True, comment="알림 활성화 여부")
    last_status = Column(String(10), default='CLOSE', comment="마지막 방송 상태 (OPEN/CLOSE)")
    last_notified_at = Column(DateTime(timezone=True), nullable=True, comment="마지막 알림 전송 시간")

    __table_args__ = (
        UniqueConstraint('chzzk_channel_id', 'discord_channel_id', name='unique_chzzk_discord_notification'),
    )


class V2Channel(Base):
    __tablename__ = "v2_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    platform = Column(String(50), nullable=False)
    platform_channel_id = Column(String(255), nullable=False)
    channel_name = Column(String(255), nullable=False)
    profile_image_url = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("platform", "platform_channel_id", name="unique_v2_platform_channel"),
    )


class V2PlatformCredential(Base):
    __tablename__ = "v2_platform_credentials"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    platform = Column(String(50), nullable=False)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    token_type = Column(String(50), nullable=True)
    scope = Column(Text, nullable=True)
    raw_token_response = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "platform", name="unique_v2_platform_credentials_channel_platform"),
    )


class V2ChannelConfig(Base):
    __tablename__ = "v2_channel_configs"

    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), primary_key=True)
    command_prefix = Column(String(10), nullable=False, default="!", server_default=text("'!'"))
    language = Column(String(10), nullable=False, default="ko", server_default=text("'ko'"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class V2GlobalChatCommand(Base):
    __tablename__ = "v2_global_chat_commands"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    command = Column(String(100), nullable=False)
    response = Column(Text, nullable=True)
    type = Column(String(20), nullable=False, default="text", server_default=text("'text'"))
    cooldown_seconds = Column(Integer, nullable=False, default=5, server_default=text("5"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    display_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("command", name="unique_v2_global_chat_commands_command"),
    )


class V2ChannelChatCommand(Base):
    __tablename__ = "v2_channel_chat_commands"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    command = Column(String(100), nullable=False)
    response = Column(Text, nullable=False)
    type = Column(String(20), nullable=False, default="text", server_default=text("'text'"))
    cooldown_seconds = Column(Integer, nullable=False, default=5, server_default=text("5"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "command", name="unique_v2_channel_chat_commands_channel_command"),
    )


class V2ChannelGreeting(Base):
    __tablename__ = "v2_channel_greetings"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    keyword = Column(String(100), nullable=False)
    response = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "keyword", name="unique_v2_channel_greetings_channel_keyword"),
    )


class V2ViewerAttendance(Base):
    __tablename__ = "v2_viewer_attendance"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    platform_user_id = Column(String(255), nullable=False)
    user_name = Column(String(255), nullable=True)
    attendance_count = Column(Integer, nullable=False, default=1, server_default=text("1"))
    streak_count = Column(Integer, nullable=False, default=1, server_default=text("1"))
    last_attendance_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "platform_user_id", name="unique_v2_viewer_attendance_channel_user"),
    )

    @property
    def user_id(self):
        return self.platform_user_id


class V2StreamSession(Base):
    __tablename__ = "v2_stream_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    stream_title = Column(String(255), nullable=True)
    category = Column(String(255), nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    raw_live_response = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "opened_at", name="unique_v2_stream_sessions_channel_opened_at"),
        Index("idx_v2_stream_sessions_channel_opened_at", "channel_id", opened_at.desc()),
        Index("idx_v2_stream_sessions_open", "channel_id", postgresql_where=closed_at.is_(None)),
    )


class V2ChannelLiveState(Base):
    __tablename__ = "v2_channel_live_states"

    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(20), nullable=False, default="UNKNOWN", server_default=text("'UNKNOWN'"))
    current_stream_session_id = Column(UUID(as_uuid=True), ForeignKey("v2_stream_sessions.id", ondelete="SET NULL"), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    raw_status = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSE', 'UNKNOWN')", name="chk_v2_channel_live_states_status"),
        Index("idx_v2_channel_live_states_current_stream_session_id", "current_stream_session_id"),
    )


class V2LiveNotification(Base):
    __tablename__ = "v2_live_notifications"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    destination_platform = Column(String(50), nullable=False)
    destination_channel_id = Column(String(255), nullable=False)
    mention_role = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "destination_platform",
            "destination_channel_id",
            name="unique_v2_live_notifications_destination",
        ),
    )

    @property
    def discord_channel_id(self):
        return self.destination_channel_id

    @discord_channel_id.setter
    def discord_channel_id(self, value):
        self.destination_channel_id = value


class V2LiveNotificationDelivery(Base):
    __tablename__ = "v2_live_notification_deliveries"

    id = Column(BigInteger, Identity(always=True), primary_key=True)
    notification_id = Column(BigInteger, ForeignKey("v2_live_notifications.id", ondelete="CASCADE"), nullable=False)
    stream_session_id = Column(UUID(as_uuid=True), ForeignKey("v2_stream_sessions.id", ondelete="CASCADE"), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivery_status = Column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("notification_id", "stream_session_id", name="unique_v2_live_notification_delivery"),
        CheckConstraint("delivery_status IN ('pending', 'success', 'failed')", name="chk_v2_live_notification_deliveries_status"),
        Index("idx_v2_live_notification_deliveries_stream_session_id", "stream_session_id"),
    )
