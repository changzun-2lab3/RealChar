import asyncio
import os
import uuid
from typing import Optional, NoReturn
from dotenv import load_dotenv

from whatsapp_api_client_python.response import Response
from whatsapp_chatbot_python import GreenAPIBot, Notification, GreenAPIError

from realtime_ai_character.chatbot import Conversation, init_chatbot
from realtime_ai_character.logger import get_logger


# environment
load_dotenv()
logger = get_logger(__name__)


# variables
bot = GreenAPIBot(
    os.getenv('GREENAPI_CHATBOT_ID'),
    os.getenv('GREENAPI_CHATBOT_TOKEN')
)
user_conversations: dict = {}
conversations: dict = {}


@bot.router.outgoing_api_message() # for testing api with one account
# @bot.router.message()
def message_handler(notification: Notification) -> None:
    logger.info('handling notification: ' + notification.event['typeWebhook'])
    logger.info('sender id: ' + notification.sender)
    logger.info('sender name: ' + notification.event['senderData']['senderName'])
    logger.info('message: ' + notification.message_text)

    if notification.event['typeWebhook'] == 'incomingMessageReceived' or notification.event['typeWebhook'] == 'outgoingAPIMessageReceived':
        sender_id = notification.sender
        sender_name = notification.event['senderData']['senderName']
        message = notification.message_text

        if message.startswith('AI:'): # prevent answering to another AI
            logger.info('Trapped AI message notification, message: ' + message)
            return

        if not sender_name:
            sender_name = 'Anonymous' # TODO: find a better name for unknown person

        conversation: Conversation
        conversation_id = user_conversations.get(sender_id)

        if not conversation_id:
            logger.info('Creating conversation for user: ' + sender_id)
            conversation_id = str(uuid.uuid4().hex)[:16]
            user_conversations[sender_id] = conversation_id
            conversation = Conversation(conversation_id, sender_name)
            conversations[conversation_id] = conversation
        else:
            conversation = conversations.get(conversation_id)
            if not conversation:
                logger.info('Conversation lost, recreating for user: ' + sender_id)
                conversation_id = str(uuid.uuid4().hex)[:16]
                user_conversations[sender_id] = conversation_id
                conversation = Conversation(conversation_id, sender_name)
                conversations[conversation_id] = conversation

        def callback(response: str):
            logger.info('AI response: ' + response)
            notification.answer('AI: ' + response)  # use prefix temporarily

        logger.info('Start response on conversation: ' + conversation_id + ' for user: ' + sender_id)
        asyncio.run(conversation.answer(message, callback))


def __validate_response(response: Response) -> Optional[NoReturn]:
    if response.code != 200:
        if response.error:
            raise GreenAPIError(response.error)
        raise GreenAPIError(
            f'GreenAPI error occurred with status code {response.code}'
        )


def main():
    # init
    init_chatbot()

    # message request loop
    while True:
        try:
            logger.info('getting request')
            response = bot.api.receiving.receiveNotification()

            __validate_response(response)

            if not response.data:
                continue

            body = response.data['body']
            bot.router.route_event(body)

            __validate_response(bot.api.receiving.deleteNotification(response.data['receiptId']))
        except KeyboardInterrupt:
            break


# start app
main()
