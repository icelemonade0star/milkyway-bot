from app.chzzk.api_client import ChzzkAPIClient
from app.chzzk.base_socket_client import BaseSocketClient
from app.chzzk.handler.chat_handler import ChatHandler
from app.chzzk.handler.donation_handler import DonationHandler

api_client = ChzzkAPIClient("ACCESS_TOKEN") #TODO ACCESS_TOKEN 삽입필.
client = BaseSocketClient(api_client)

# 핸들러 등록 (동적으로 추가/제거 가능)
client.register_handler("CHAT", ChatHandler())
client.register_handler("DONATION", DonationHandler())

client.start(channel_id="YOUR_CHANNEL_ID")