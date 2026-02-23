from abc import ABC, abstractmethod

class BaseChatClient(ABC):

    @abstractmethod
    async def connect(self, url: str):
        """플랫폼의 챗 서버에 연결합니다."""
        pass

    @abstractmethod
    async def disconnect(self):
        """연결을 종료합니다."""
        pass