from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from app.core.topics_manager import get_manager_group_id
from app.db.database import async_session_maker
from app.db.models import User

GROUP_BOOTSTRAP_COMMANDS = {"report", "setup_topics", "reset_topics", "groupid", "set_manager_group"}


def _extract_command_name(obj: Union[Message, CallbackQuery]) -> str | None:
    text = obj.message.text if isinstance(obj, CallbackQuery) else obj.text
    if not text or not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0][1:]


class AdminFilter(BaseFilter):
    async def __call__(self, obj: Union[Message, CallbackQuery]) -> bool:
        user_id = obj.from_user.id
        async with async_session_maker() as session:
            user = await session.get(User, user_id)
            if user and user.is_admin:
                return True

        chat = obj.message.chat if isinstance(obj, CallbackQuery) else obj.chat
        if not chat or chat.type not in {"group", "supergroup"}:
            return False

        try:
            member = await obj.bot.get_chat_member(chat.id, user_id)
        except Exception:
            return False

        if member.status not in {"administrator", "creator"}:
            return False

        command_name = _extract_command_name(obj)
        if command_name in GROUP_BOOTSTRAP_COMMANDS:
            return True

        manager_group_id = get_manager_group_id()
        return manager_group_id is not None and chat.id == manager_group_id
