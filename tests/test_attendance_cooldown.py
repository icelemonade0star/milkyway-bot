import asyncio
from types import SimpleNamespace

from app.features.chat.handling import handler


class FakeChatService:
    def __init__(self, db):
        self.db = db

    async def get_chat_command(self, channel_id, command, platform):
        return None

    async def get_global_commands(self, command):
        return SimpleNamespace(
            command=command,
            type="attendance",
            is_active=True,
            cooldown_seconds=5,
        )

    async def process_attendance(self, channel_id, user_id, user_name, platform):
        return {"status": "checked", "streak": 1, "total": 1}


class FakeRedisService:
    def __init__(self):
        self.cooldown_keys = set()

    async def check_and_set_cooldown(self, channel_id, command, cooldown_seconds, platform):
        key = (channel_id, command)
        if key in self.cooldown_keys:
            return True
        self.cooldown_keys.add(key)
        return False


class FakeSession:
    def __init__(self):
        self.messages = []

    async def send_chat(self, message):
        self.messages.append(message)


def test_global_attendance_cooldown_is_applied_per_user(monkeypatch):
    monkeypatch.setattr(handler, "ChatService", FakeChatService)
    redis_service = FakeRedisService()
    session = FakeSession()

    async def run_attendance():
        for user_id, user_name in (("user-a", "A"), ("user-b", "B")):
            await handler.on_command(
                db=object(),
                session=session,
                channel_id="channel-1",
                command="출석",
                args=[],
                role="common_user",
                redis_service=redis_service,
                prefix="!",
                user_id=user_id,
                user_name=user_name,
            )

    asyncio.run(run_attendance())

    assert len(session.messages) == 2
    assert redis_service.cooldown_keys == {
        ("channel-1", "출석:user:user-a"),
        ("channel-1", "출석:user:user-b"),
    }
