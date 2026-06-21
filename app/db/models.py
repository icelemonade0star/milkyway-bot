from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

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
