import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.sql import func

Base = declarative_base()

class V2Channel(Base):
    __tablename__ = "v2_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("platform", "platform_channel_id", name="unique_v2_platform_channel"),
    )


class V2PlatformCredential(Base):
    __tablename__ = "v2_platform_credentials"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_token_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "platform", name="unique_v2_platform_credentials_channel_platform"),
    )


class V2ChannelConfig(Base):
    __tablename__ = "v2_channel_configs"

    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), primary_key=True)
    command_prefix: Mapped[str] = mapped_column(String(10), nullable=False, default="!", server_default=text("'!'"))
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="ko", server_default=text("'ko'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class V2OverlaySetting(Base):
    __tablename__ = "v2_overlay_settings"

    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), primary_key=True)
    overlay_kind: Mapped[str] = mapped_column(String(20), primary_key=True, default="chat", server_default=text("'chat'"))
    style_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="options", server_default=text("'options'"))
    style_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    custom_css: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("style_mode IN ('options', 'custom')", name="check_v2_overlay_settings_style_mode"),
        CheckConstraint("overlay_kind IN ('chat', 'timer')", name="check_v2_overlay_settings_overlay_kind"),
    )


class V2OverlayPreset(Base):
    __tablename__ = "v2_overlay_presets"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    overlay_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="chat", server_default=text("'chat'"))
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    style_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="options", server_default=text("'options'"))
    style_options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    custom_css: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("style_mode IN ('options', 'custom')", name="check_v2_overlay_presets_style_mode"),
        CheckConstraint("overlay_kind IN ('chat', 'timer')", name="check_v2_overlay_presets_overlay_kind"),
        UniqueConstraint("channel_id", "overlay_kind", "name", name="unique_v2_overlay_presets_channel_kind_name"),
        Index("idx_v2_overlay_presets_channel_kind", "channel_id", "overlay_kind"),
    )


class V2GlobalChatCommand(Base):
    __tablename__ = "v2_global_chat_commands"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    command: Mapped[str] = mapped_column(String(100), nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="text", server_default=text("'text'"))
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default=text("5"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("command", name="unique_v2_global_chat_commands_command"),
    )


class V2ChannelChatCommand(Base):
    __tablename__ = "v2_channel_chat_commands"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    command: Mapped[str] = mapped_column(String(100), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="text", server_default=text("'text'"))
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default=text("5"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "command", name="unique_v2_channel_chat_commands_channel_command"),
    )


class V2ChannelGreeting(Base):
    __tablename__ = "v2_channel_greetings"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "keyword", name="unique_v2_channel_greetings_channel_keyword"),
    )


class V2ViewerAttendance(Base):
    __tablename__ = "v2_viewer_attendance"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attendance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    streak_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    last_attendance_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "platform_user_id", name="unique_v2_viewer_attendance_channel_user"),
    )

class V2StreamSession(Base):
    __tablename__ = "v2_stream_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stream_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_live_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("channel_id", "opened_at", name="unique_v2_stream_sessions_channel_opened_at"),
    )


Index("idx_v2_stream_sessions_channel_opened_at", V2StreamSession.channel_id, V2StreamSession.opened_at.desc())
Index("idx_v2_stream_sessions_open", V2StreamSession.channel_id, postgresql_where=V2StreamSession.closed_at.is_(None))


class V2ChannelLiveState(Base):
    __tablename__ = "v2_channel_live_states"

    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNKNOWN", server_default=text("'UNKNOWN'"))
    current_stream_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_stream_sessions.id", ondelete="SET NULL"), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSE', 'UNKNOWN')", name="chk_v2_channel_live_states_status"),
        Index("idx_v2_channel_live_states_current_stream_session_id", "current_stream_session_id"),
    )


class V2LiveNotification(Base):
    __tablename__ = "v2_live_notifications"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_channels.id", ondelete="CASCADE"), nullable=False)
    destination_platform: Mapped[str] = mapped_column(String(50), nullable=False)
    destination_channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    mention_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "destination_platform",
            "destination_channel_id",
            name="unique_v2_live_notifications_destination",
        ),
    )

class V2LiveNotificationDelivery(Base):
    __tablename__ = "v2_live_notification_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    notification_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("v2_live_notifications.id", ondelete="CASCADE"), nullable=False)
    stream_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v2_stream_sessions.id", ondelete="CASCADE"), nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default=text("'pending'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("notification_id", "stream_session_id", name="unique_v2_live_notification_delivery"),
        CheckConstraint("delivery_status IN ('pending', 'success', 'failed')", name="chk_v2_live_notification_deliveries_status"),
        Index("idx_v2_live_notification_deliveries_stream_session_id", "stream_session_id"),
    )
