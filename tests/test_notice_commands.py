import asyncio
import os
from unittest.mock import AsyncMock

import httpx
import pytest

os.environ.setdefault("CLIENT_SECRET", "test-client-secret")

from app.features.chat.handling.cmd_chat import handle_clear_notice, handle_notice
from app.platforms.chzzk import chat


def make_session():
    session = chat.ChzzkSessions("channel")
    session.access_token = "test-access-token"
    return session


def stub_responses(monkeypatch, *status_codes):
    post = AsyncMock(side_effect=[httpx.Response(code) for code in status_codes])
    monkeypatch.setattr(chat._client, "post", post)
    return post


def sent_messages(post):
    return [call.kwargs["json"]["message"] for call in post.await_args_list]


def test_clear_notice_stops_at_first_accepted_candidate(monkeypatch):
    post = stub_responses(monkeypatch, 200)
    assert asyncio.run(make_session().clear_notice()) == (True, "")
    assert sent_messages(post) == [""]


def test_clear_notice_falls_back_when_candidate_is_rejected(monkeypatch):
    post = stub_responses(monkeypatch, 400, 200)
    success, applied = asyncio.run(make_session().clear_notice())
    assert (success, applied) == (True, chat.NOTICE_CLEAR_CANDIDATES[1])
    assert sent_messages(post) == list(chat.NOTICE_CLEAR_CANDIDATES[:2])


def test_clear_notice_tries_every_candidate_before_failing(monkeypatch):
    post = stub_responses(monkeypatch, *[400] * len(chat.NOTICE_CLEAR_CANDIDATES))
    assert asyncio.run(make_session().clear_notice()) == (False, "")
    assert sent_messages(post) == list(chat.NOTICE_CLEAR_CANDIDATES)


# 401 재시도는 send_notice와 clear_notice가 _request_notice를 통해 공유합니다.
def test_notice_request_retries_once_after_token_refresh(monkeypatch):
    post = stub_responses(monkeypatch, 401, 200)
    session = make_session()
    monkeypatch.setattr(session, "_refresh_token", AsyncMock(return_value=True))
    assert asyncio.run(session.clear_notice()) == (True, "")
    assert post.await_count == 2


def test_notice_request_does_not_retry_when_refresh_fails(monkeypatch):
    post = stub_responses(monkeypatch, *[401] * len(chat.NOTICE_CLEAR_CANDIDATES))
    session = make_session()
    monkeypatch.setattr(session, "_refresh_token", AsyncMock(return_value=False))
    assert asyncio.run(session.clear_notice()) == (False, "")
    assert post.await_count == len(chat.NOTICE_CLEAR_CANDIDATES)


def test_send_notice_rejects_blank_message_without_calling_api(monkeypatch):
    post = stub_responses(monkeypatch, 200)
    assert asyncio.run(make_session().send_notice("   ")) is False
    post.assert_not_awaited()


@pytest.mark.parametrize("result,expected", [
    ((True, ""), "공지를 삭제했습니다."),
    ((True, chat.NOTICE_CLEAR_CANDIDATES[-1]), "공지를 비웠습니다. 치지직은 공지 삭제를 지원하지 않아 빈 공지로 남습니다."),
    ((False, ""), "공지 삭제에 실패했습니다."),
])
def test_clear_notice_handler_reports_actual_outcome(result, expected):
    session = AsyncMock(clear_notice=AsyncMock(return_value=result))
    asyncio.run(handle_clear_notice(session))
    session.send_chat.assert_awaited_once_with(expected)


def test_notice_handler_still_requires_content():
    session = AsyncMock()
    asyncio.run(handle_notice(session, []))
    session.send_notice.assert_not_awaited()
    session.send_chat.assert_awaited_once_with("사용법: !공지 [내용]")
