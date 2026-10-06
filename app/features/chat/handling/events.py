from app.core.logger import get_channel_logger


async def on_donation(channel_id: str, payload: dict):
    """후원 이벤트 진입점. 후속 기능에서 원본 필드를 그대로 사용할 수 있다."""
    logger = get_channel_logger(channel_id)
    logger.info(
        "후원 수신: donationType=%s, donatorChannelId=%s, 닉네임=%s, 금액=%s원, 메시지=%s",
        payload.get("donationType"), payload.get("donatorChannelId"),
        payload.get("donatorNickname"), payload.get("payAmount"), payload.get("donationText"),
    )


async def on_subscription(channel_id: str, payload: dict):
    """구독 이벤트 진입점. 구독 상품과 기간은 API 원본 값을 유지한다."""
    logger = get_channel_logger(channel_id)
    logger.info(
        "구독 수신: subscriberChannelId=%s, 닉네임=%s, tierNo=%s, tierName=%s, month=%s",
        payload.get("subscriberChannelId"), payload.get("subscriberNickname"),
        payload.get("tierNo"), payload.get("tierName"), payload.get("month"),
    )
