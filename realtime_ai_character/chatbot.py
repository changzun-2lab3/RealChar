import asyncio
import os
import uuid
from typing import Callable

from realtime_ai_character.character_catalog.catalog_manager import get_catalog_manager, CatalogManager
from realtime_ai_character.llm import get_llm, LLM
from realtime_ai_character.llm.base import AsyncCallbackTextHandler, AsyncCallbackAudioHandler
from realtime_ai_character.utils import ConversationHistory, build_history, Character


default_character: Character = None


class DummyAsyncCallbackTextHandler(AsyncCallbackTextHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    async def on_chat_model_start(self, *args, **kwargs):
        pass


    async def on_llm_new_token(self, token: str, *args, **kwargs):
        pass


    async def on_llm_end(self, *args, **kwargs):
        pass


class DummyAsyncCallbackAudioHandler(AsyncCallbackAudioHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    async def on_chat_model_start(self, *args, **kwargs):
        pass


    async def on_llm_new_token(self, token: str, *args, **kwargs):
        pass


    async def on_llm_end(self, *args, **kwargs):
        pass


class Conversation:
    conversation_id: str
    listener_name: str
    character: Character
    conversation_history: ConversationHistory
    llm: LLM


    def __init__(
            self,
            _conversation_id: str,
            _listener_name: str,
            character_id: str = None
    ):
        self.conversation_id = _conversation_id
        self.listener_name = _listener_name
        self.conversation_history = ConversationHistory()
        self.llm = get_llm(model=os.getenv('LLM_MODEL_USE', 'gpt-3.5-turbo-16k'))

        # init character
        global default_character
        self.character = default_character
        if character_id:
            catalog_manager: CatalogManager = get_catalog_manager()
            characters: dict = catalog_manager.characters
            self.character = characters.get(character_id)

            if not self.character:
                self.character = default_character


    async def answer(
            self,
            message: str,
            callback: Callable[[str], None]
    ):
        message_id = str(uuid.uuid4().hex)[:16]
        response = await self.llm.achat(
            history=build_history(self.conversation_history),
            user_input=message,
            user_input_template=self.character.llm_user_prompt,
            callback=DummyAsyncCallbackTextHandler(),
            audioCallback=DummyAsyncCallbackAudioHandler,
            character=self.character,
            useSearch=False,
            useQuivr=False,
            quivrApiKey=None,
            quivrBrainId=None,
            useMultiOn=False,
            metadata={'message_id': message_id})

        self.conversation_history.user.append(message)
        self.conversation_history.ai.append(response)

        callback(response)


def init_chatbot() -> None:
    # init LLM
    get_llm(model=os.getenv('LLM_MODEL_USE', 'gpt-3.5-turbo-16k'))

    # init character
    global default_character
    catalog_manager: CatalogManager = get_catalog_manager()
    characters: dict = catalog_manager.characters

    if not characters:
        raise RuntimeError('No character in database')

    default_character = characters.get(os.getenv('CHATBOT_CHARACTER', 'elon_musk'))
    if not default_character:
        default_character = next(iter(characters.values()))
