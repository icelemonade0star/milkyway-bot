import logging
import re
from app.redis.redis_service import RedisConfigService

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_session_factory
from app.db.models import ChzzkNotification
from app.features.chat.service import ChatService
from app.core.config import ALLOWED_PREFIXES
from app.features.discord_bot.cogs.discord_service import DiscordService

# 로거 설정
logger = logging.getLogger("MessageHandling")

# 헬퍼 함수: 접두사 제거
def strip_prefix(text: str) -> str:
    if text and text[0] in ALLOWED_PREFIXES:
        return text[1:]
    return text

# 헬퍼 함수: 이모티콘 체크
def has_chzzk_emoticon(text: str) -> bool:
    return bool(re.search(r'{:[a-zA-Z0-9_]+:}', text))

# 헬퍼 함수: 한국어 조사 판별
def get_josa(word: str, josa_pair: str) -> str:
    """
    입력된 단어의 받침 유무에 따라 적절한 조사를 반환합니다.
    사용법: get_josa("사과", "은/는") -> "는", get_josa("수박", "이/가") -> "이"
    """
    if not word:
        return ""
    last_char = word[-1]
    first, second = josa_pair.split('/')
    # 한글 유니코드 범위 (가 ~ 힣) 확인
    if 0xAC00 <= ord(last_char) <= 0xD7A3:
        # (문자코드 - 0xAC00) % 28 > 0 이면 받침 있음
        has_batchim = (ord(last_char) - 0xAC00) % 28 > 0
        return first if has_batchim else second
    # 숫자인 경우 발음에 따라 조사 결정
    elif last_char.isdigit():
        # 0(영), 1(일), 3(삼), 6(육), 7(칠), 8(팔) -> 받침 있음
        return first if last_char in "013678" else second
    # 한글, 숫자가 아닌 경우(영어 등) 보통 받침 없는 쪽(뒤)을 기본값으로 사용
    return second

# 헬퍼 함수: 명령어 인자 파싱 ( | 포함 공백 처리 )
def parse_command_and_content(args_list):
    if not args_list:
        return None, None
    
    raw_cmd = args_list[0]
    idx = 1
    
    # 파이프(|)가 포함된 명령어가 공백으로 분리된 경우를 처리
    # 예: "룰| 규칙", "룰 |규칙", "룰 | 규칙" 등
    while idx < len(args_list):
        next_arg = args_list[idx]
        if raw_cmd.endswith('|') or next_arg.startswith('|'):
            raw_cmd += next_arg
            idx += 1
        else:
            break
        
    cmd_no_prefix = strip_prefix(raw_cmd)
    # | 기준으로 분리 후 각 항목의 공백 제거 및 빈 항목 필터링
    cleaned_parts = [p.strip() for p in cmd_no_prefix.split('|') if p.strip()]
    final_cmd = "|".join(cleaned_parts)
    
    # 남은 args를 content로 결합
    content = " ".join(args_list[idx:]) if idx < len(args_list) else ""
    
    return final_cmd, content

async def on_message(channel_id: str, message_text: str, role: str, user_id: str, user_name: str):
    # 순환 참조 방지를 위해 함수 내부에서 import
    from app.features.chat.session_manager import session_manager
   
    # 1. Redis 서비스 인스턴스 생성
    redis_service = RedisConfigService()
    
    # 2. Prefix 조회 (Redis -> DB Fallback)
    prefix = await redis_service.get_command_prefix(channel_id)
    
    # 접두사로 시작하지 않으면 인삿말(Greeting) 체크
    if not message_text.startswith(prefix):
        # DB 세션 팩토리 확인
        session_factory = get_session_factory()
        if session_factory:
            # 인삿말 체크 및 응답
            greeting_resp = await redis_service.get_greeting_response(channel_id, message_text.strip())
            if greeting_resp:
                # 인삿말 감지 시 출석 체크 수행
                async with session_factory() as db:
                    chat_service = ChatService(db)
                    # 출석 로직 실행
                    await chat_service.process_attendance(channel_id, user_id, user_name)

                session = await session_manager.get_session(channel_id)
                if session:
                    await session.send_chat(greeting_resp)
        return

    # 3. 명령어 파싱
    content = message_text[len(prefix):].strip()
    if not content:
        return # 접두사만 있는 경우

    parts = content.split()
    command = parts[0]
    args = parts[1:]

    # 4. DB 연결 및 명령어 실행
    session_factory = get_session_factory()
    if not session_factory:
        logger.error("DB Session Factory is not initialized.")
        return

    async with session_factory() as db:
        session = await session_manager.get_session(channel_id)
        if session:
            await on_command(db, session, channel_id, command, args, role, redis_service, prefix, user_id, user_name)

async def on_command(db: AsyncSession, session, channel_id: str, command: str, args: list, role: str, redis_service: RedisConfigService, prefix: str, user_id: str, user_name: str):
    chat_service = ChatService(db)
    
    # 1. 커스텀 명령어 우선 조회 (개인화/오버라이딩)
    custom_cmd = await chat_service.get_chat_command(channel_id, command)
    if custom_cmd and custom_cmd.is_active:
        # 쿨타임 체크
        if await redis_service.check_and_set_cooldown(channel_id, command, custom_cmd.cooldown_seconds):
            return

        if custom_cmd.type == 'global':
            # response 값을 명령어 이름으로 사용하여 글로벌 명령어 로직으로 진입
            command = custom_cmd.response
        else:
            await session.send_chat(custom_cmd.response)
            return

    # 2. 글로벌 명령어 조회
    result = await chat_service.get_global_commands(command)

    if result and result.is_active:
        # 쿨타임 체크
        if await redis_service.check_and_set_cooldown(channel_id, command, result.cooldown_seconds):
            return

        if result.type == "text":
            # 텍스트 응답 전송
            await session.send_chat(result.response)
            
        elif result.type == "system":
            # 시스템 명령어 처리
            # 관리자 권한이 필요한 명령어 목록
            admin_commands = ["명령어등록", "명령어삭제", "접두사수정", "인사등록", "인사삭제", "알림설정", "알림삭제"]
            if result.command in admin_commands and role == 'common_user':
                return

            if result.command == "명령어":
                # 모든 활성 글로벌 명령어 조회
                all_cmds = await chat_service.get_all_global_commands()
                if all_cmds:
                    cmd_names = [cmd.command.split('|')[0].strip() for cmd in all_cmds]
                    response_message = f"기본 명령어: {', '.join(cmd_names)}"
                    await session.send_chat(response_message)
            
            elif result.command == "채널명령어":
                # 채널 전용 커스텀 명령어 조회
                channel_cmds = await chat_service.get_channel_commands(channel_id)
                if channel_cmds:
                    cmd_names = [cmd.command.split('|')[0].strip() for cmd in channel_cmds]
                    response_message = f"채널 명령어: {', '.join(cmd_names)}"
                    await session.send_chat(response_message)
                else:
                    await session.send_chat("등록된 채널 명령어가 없습니다.")
            
            elif result.command == "명령어등록":
                if len(args) < 2:
                    await session.send_chat("사용법: !명령어등록 [명령어] [내용]")
                    return
                
                new_cmd, new_response = parse_command_and_content(args)
                if not new_cmd or not new_response:
                    await session.send_chat("명령어와 내용을 모두 입력해주세요.")
                    return

                if has_chzzk_emoticon(new_cmd) or has_chzzk_emoticon(new_response):
                    await session.send_chat("명령어 또는 내용에 이모티콘을 포함할 수 없습니다.")
                    return

                # 명령어 등록 전에 기존 명령어 존재 여부 확인 (업데이트/등록 구분)
                existing_cmd = await chat_service.get_chat_command(channel_id, new_cmd)
                
                # 명령어 등록/업데이트 시 글로벌 명령어와의 충돌 체크
                success = await chat_service.add_chat_command(channel_id, new_cmd, new_response)
                
                if success:
                    josa = get_josa(new_cmd, "이/가")
                    if existing_cmd:
                        await session.send_chat(f"명령어 '{new_cmd}'{josa} 수정되었습니다.")
                    else:
                        await session.send_chat(f"명령어 '{new_cmd}'{josa} 등록되었습니다.")
                else:
                    # This case is for global command conflict
                    await session.send_chat(f"'{new_cmd}'는 이미 존재하는 기본 명령어이거나 등록할 수 없는 명령어입니다.")

            elif result.command == "명령어삭제":
                if len(args) < 1:
                    await session.send_chat("사용법: 명령어삭제 [명령어]")
                    return
                
                target_cmd, _ = parse_command_and_content(args)
                if not target_cmd:
                    await session.send_chat("삭제할 명령어를 입력해주세요.")
                    return

                success = await chat_service.delete_chat_command(channel_id, target_cmd)
                if success:
                    josa = get_josa(target_cmd, "이/가")
                    await session.send_chat(f"명령어 '{target_cmd}'{josa} 삭제되었습니다.")
                else:
                    await session.send_chat(f"존재하지 않는 명령어입니다: {target_cmd}")

            elif result.command == "접두사수정":
                if len(args) < 1:
                    await session.send_chat("사용법: 접두사수정 [새접두사]")
                    return
                new_prefix = args[0]

                # 접두사 화이트리스트 검증
                if len(new_prefix) != 1 or new_prefix not in ALLOWED_PREFIXES:
                    await session.send_chat(f"허용되지 않는 접두사입니다. 사용 가능: {ALLOWED_PREFIXES}")
                    return

                # RedisConfigService를 통해 DB와 Redis 모두 업데이트
                redis_service = RedisConfigService()
                await redis_service.update_command_prefix(channel_id, new_prefix)
                josa = get_josa(new_prefix, "으로/로")
                await session.send_chat(f"접두사가 '{new_prefix}'{josa} 변경되었습니다.")

            # --- 인삿말 관리 명령어 ---
            elif result.command == "인사등록":
                if len(args) < 2:
                    await session.send_chat("사용법: !인사등록 [키워드] [응답]")
                    return
                
                keywords_str, response = parse_command_and_content(args)
                if not keywords_str or not response:
                    await session.send_chat("키워드와 응답을 모두 입력해주세요.")
                    return
                
                if has_chzzk_emoticon(response):
                    await session.send_chat("인삿말 내용에 이모티콘을 포함할 수 없습니다.")
                    return

                keywords = keywords_str.split('|')
                created_list = []
                updated_list = []
                
                for keyword in keywords:
                    # Check existence first
                    existing = await chat_service.get_greeting(channel_id, keyword)
                    if existing:
                        # Update
                        if await chat_service.update_greeting(channel_id, keyword, response):
                            await redis_service.add_greeting_cache(channel_id, keyword, response)
                            updated_list.append(keyword)
                    else:
                        # Create
                        if await chat_service.create_greeting(channel_id, keyword, response):
                            await redis_service.add_greeting_cache(channel_id, keyword, response)
                            created_list.append(keyword)
                
                response_messages = []
                if created_list:
                    created_str = ", ".join([f"'{k}'" for k in created_list])
                    response_messages.append(f"인삿말 {created_str}이(가) 등록되었습니다.")
                if updated_list:
                    updated_str = ", ".join([f"'{k}'" for k in updated_list])
                    response_messages.append(f"인삿말 {updated_str}이(가) 수정되었습니다.")
                
                if response_messages:
                    await session.send_chat(" ".join(response_messages))
                else:
                    await session.send_chat("이미 등록되었거나, 처리에 실패했습니다.")

            elif result.command == "인사삭제":
                if len(args) < 1:
                    await session.send_chat("사용법: !인사삭제 [키워드]")
                    return
                
                keywords_str, _ = parse_command_and_content(args)
                if not keywords_str:
                    await session.send_chat("삭제할 키워드를 입력해주세요.")
                    return

                keywords = keywords_str.split('|')
                success_list = []

                for keyword in keywords:
                    if await chat_service.delete_greeting(channel_id, keyword):
                        await redis_service.delete_greeting_cache(channel_id, keyword) # Redis에서 삭제
                        success_list.append(keyword)
                
                if success_list:
                    success_str = ", ".join([f"'{k}'" for k in success_list])
                    await session.send_chat(f"인삿말 {success_str}이(가) 삭제되었습니다.")
                elif not success_list:
                    await session.send_chat(f"등록되지 않은 인삿말입니다.")

            elif result.command == "인사목록":
                greetings = await chat_service.get_channel_greetings(channel_id)
                if greetings:
                    keywords = [g.keyword for g in greetings]
                    await session.send_chat(f"등록된 인삿말: {', '.join(keywords)}")
                else:
                    await session.send_chat("등록된 인삿말이 없습니다.")

            elif result.command == "알림설정":
                
                if len(args) < 1:
                    await session.send_chat("사용법: 우선, !디스코드봇으로 나온 url로 디스코드에 봇을 초대해주세요. 그리고 채팅창에 !알림설정 [디스코드채널ID]를 입력하세요.")
                    return
                
                discord_channel_id = args[0]

                # [검증] 디스코드 메시지 발송 테스트
                discord_service = DiscordService()
                test_msg = f"🔔 [MilkywayBot] '{user_name}'님의 방송 알림이 이 채널로 정상적으로 설정되었습니다."
                
                if not await discord_service.send_message(discord_channel_id, test_msg):
                    await session.send_chat(f"❌ 설정 실패: 디스코드 채널({discord_channel_id})에 테스트 메시지를 보낼 수 없습니다. 봇이 초대되었는지, 채널 ID가 맞는지 확인해주세요.")
                    return
                
                stmt = select(ChzzkNotification).where(ChzzkNotification.chzzk_channel_id == channel_id)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                
                if existing:
                    existing.discord_channel_id = discord_channel_id
                    existing.streamer_name = user_name
                    existing.is_active = True
                    await session.send_chat(f"알림 설정이 업데이트되었습니다. (Discord ID: {discord_channel_id})")
                else:
                    new_noti = ChzzkNotification(chzzk_channel_id=channel_id, streamer_name=user_name, discord_channel_id=discord_channel_id, last_status="CLOSE", is_active=True)
                    db.add(new_noti)
                    await session.send_chat(f"알림 설정이 등록되었습니다. (Discord ID: {discord_channel_id})")
                await db.commit()

            elif result.command == "알림삭제":
                stmt = select(ChzzkNotification).where(ChzzkNotification.chzzk_channel_id == channel_id)
                existing = (await db.execute(stmt)).scalar_one_or_none()
                
                if existing and existing.is_active:
                    existing.is_active = False
                    await db.commit()
                    await session.send_chat("알림 설정이 해제되었습니다.")
                else:
                    await session.send_chat("활성화된 알림 설정이 없습니다.")

        elif result.type == "attendance":
            result_att = await chat_service.process_attendance(channel_id, user_id, user_name)
            if result_att:
                if result_att["status"] == "checked":
                    msg = f"@{user_name}님 출석 체크 완료! 총 {result_att['total']}회)"
                    await session.send_chat(msg)
                elif result_att["status"] == "already_checked":
                    msg = f"@{user_name}님 이미 오늘 출석하셨습니다. 총 {result_att['total']}회)"
                    await session.send_chat(msg)
