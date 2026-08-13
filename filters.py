"""Custom bot filters: whitelist users/groups with cached admin checks."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import telebot
import telebot.asyncio_filters

_AdminCacheKey = tuple[int, int]


class AdminCache:
    """Bounded TTL cache for group-admin lookups (LRU eviction + TTL)."""

    def __init__(
        self,
        ttl_seconds: float = 3600,
        maxsize: int = 1024,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        self._now = now
        self._data: OrderedDict[_AdminCacheKey, tuple[bool, float]] = OrderedDict()

    def get(self, key: _AdminCacheKey) -> bool | None:
        cached = self._data.get(key)
        if cached is None:
            return None
        is_admin, ts = cached
        if self._now() - ts >= self._ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return is_admin

    def set(self, key: _AdminCacheKey, is_admin: bool) -> None:
        self._data[key] = (is_admin, self._now())
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)


class IsFromWhitelist(telebot.asyncio_filters.SimpleCustomFilter):
    """Allow whitelisted users, plus admins of whitelisted groups."""

    key = 'is_from_whitelist'

    def __init__(
        self,
        bot: Any,
        whitelist_users: tuple[int, ...],
        whitelist_groups: tuple[int, ...],
    ) -> None:
        self._bot = bot
        self._whitelist_users = whitelist_users
        self._whitelist_groups = whitelist_groups
        self._admin_cache = AdminCache()

    async def check(self, message) -> bool:
        if message.from_user is None:
            return False
        if message.from_user.id in self._whitelist_users:
            return True
        if message.chat.id in self._whitelist_groups:
            cache_key = (message.chat.id, message.from_user.id)
            cached = self._admin_cache.get(cache_key)
            if cached is not None:
                return cached
            chat_member = await self._bot.get_chat_member(
                message.chat.id, message.from_user.id
            )
            is_admin = chat_member.status in ('creator', 'administrator')
            self._admin_cache.set(cache_key, is_admin)
            return is_admin
        return False
