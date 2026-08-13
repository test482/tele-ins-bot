import time

import telebot
import telebot.asyncio_filters

from config import WHITELIST_GROUPS, WHITELIST_USERS

_ADMIN_CACHE_TTL = 3600  # seconds
# (chat_id, user_id): (is_admin, monotonic_time)
_admin_cache: dict[tuple[int, int], tuple[bool, float]] = {}


class isFromWhiteList(telebot.asyncio_filters.SimpleCustomFilter):
    key: str = "is_from_white_list"

    def __init__(self, bot):
        self._bot = bot

    async def check(self, message):
        if message.from_user.id in WHITELIST_USERS:
            return True

        if message.chat.id in WHITELIST_GROUPS:
            cache_key = (message.chat.id, message.from_user.id)
            cached = _admin_cache.get(cache_key)
            if cached is not None:
                is_admin, ts = cached
                if time.monotonic() - ts < _ADMIN_CACHE_TTL:
                    return is_admin

            chat_member = await self._bot.get_chat_member(
                message.chat.id, message.from_user.id
            )
            is_admin = chat_member.status in ("creator", "administrator")
            _admin_cache[cache_key] = (is_admin, time.monotonic())
            return is_admin

        return False
