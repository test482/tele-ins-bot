"""Unit tests for the whitelist filter and its bounded admin cache."""

import asyncio
from types import SimpleNamespace

from filters import AdminCache, IsFromWhitelist


def msg(user_id, chat_id):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=chat_id),
    )


class FakeBot:
    def __init__(self) -> None:
        self.calls = 0
        self.status = 'administrator'

    async def get_chat_member(self, chat_id, user_id):
        self.calls += 1
        return SimpleNamespace(status=self.status)


def run(coro):
    return asyncio.run(coro)


def test_whitelist_user_no_api_call():
    bot = FakeBot()
    filter_ = IsFromWhitelist(bot, (1,), ())
    assert run(filter_.check(msg(1, -100)))
    assert bot.calls == 0


def test_group_admin_fetched_and_cached():
    bot = FakeBot()
    filter_ = IsFromWhitelist(bot, (), (-100,))
    assert run(filter_.check(msg(2, -100)))
    assert bot.calls == 1
    assert run(filter_.check(msg(2, -100)))
    assert bot.calls == 1  # served from cache


def test_group_non_admin_rejected():
    bot = FakeBot()
    bot.status = 'member'
    filter_ = IsFromWhitelist(bot, (), (-100,))
    assert not run(filter_.check(msg(2, -100)))


def test_unknown_chat_rejected():
    bot = FakeBot()
    filter_ = IsFromWhitelist(bot, (), ())
    assert not run(filter_.check(msg(2, 42)))


def test_missing_from_user_rejected():
    message = SimpleNamespace(from_user=None, chat=SimpleNamespace(id=-100))
    filter_ = IsFromWhitelist(FakeBot(), (1,), (-100,))
    assert not run(filter_.check(message))


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t


def test_admin_cache_ttl_expiry():
    clock = Clock()
    cache = AdminCache(ttl_seconds=10, maxsize=10, now=clock.now)
    cache.set((1, 2), True)
    assert cache.get((1, 2)) is True
    clock.t = 10.0
    assert cache.get((1, 2)) is None


def test_admin_cache_lru_eviction():
    clock = Clock()
    cache = AdminCache(ttl_seconds=3600, maxsize=2, now=clock.now)
    cache.set((1, 1), True)
    cache.set((2, 2), False)
    cache.set((3, 3), True)  # evicts (1, 1), the least recently used
    assert cache.get((1, 1)) is None
    assert cache.get((3, 3)) is True
    assert cache.get((2, 2)) is False
