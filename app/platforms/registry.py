from app.platforms.chzzk.auth import ChzzkAuthProvider
from app.platforms.chzzk.live import ChzzkLiveProvider
from app.core.config import DEFAULT_PLATFORM

_LIVE_PROVIDERS = {}


def get_auth_provider(platform: str, *args, **kwargs):
    if platform == "chzzk":
        return ChzzkAuthProvider(*args, **kwargs)
    raise ValueError(f"Unsupported platform: {platform}")


def get_live_provider(platform: str):
    if platform == "chzzk":
        if platform not in _LIVE_PROVIDERS:
            _LIVE_PROVIDERS[platform] = ChzzkLiveProvider()
        return _LIVE_PROVIDERS[platform]
    raise ValueError(f"Unsupported platform: {platform}")
