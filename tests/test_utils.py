"""Unit tests for utils: caption truncation, chunked sending, rate limiting."""

import asyncio
from typing import Any

import telebot.apihelper

from utils import (
    RateLimiter,
    build_post_contents_from_dir,
    send_media_chunks,
    truncate_caption,
)


class FakeBot:
    def __init__(self) -> None:
        self.media_calls: list[dict[str, Any]] = []
        self.message_calls: list[dict[str, Any]] = []

    async def send_media_group(
        self, chat_id, media, disable_notification=None, reply_parameters=None, **kwargs
    ):
        self.media_calls.append(
            {
                'chat_id': chat_id,
                'media': media,
                'disable_notification': disable_notification,
                'reply_parameters': reply_parameters,
            }
        )

    async def send_message(self, chat_id, text, reply_parameters=None, **kwargs):
        self.message_calls.append(
            {'chat_id': chat_id, 'text': text, 'reply_parameters': reply_parameters}
        )


class FailingBot(FakeBot):
    async def send_media_group(self, **kwargs):
        self.media_calls.append(kwargs)
        raise telebot.apihelper.ApiException('boom', 'send_media_group', None)


def test_truncate_none():
    assert truncate_caption(None) is None


def test_truncate_short_kept():
    assert truncate_caption('hello') == 'hello'


def test_truncate_boundary_kept():
    text = 'x' * 1024
    assert truncate_caption(text) == text


def test_truncate_long():
    text = 'x' * 2000
    result = truncate_caption(text)
    assert result is not None
    assert len(result) == 1024
    assert result.endswith('...')


def test_send_chunks_splits_at_ten():
    bot = FakeBot()
    media: list[Any] = [object() for _ in range(25)]
    asyncio.run(send_media_chunks(bot, 1, 2, media))
    assert [len(call['media']) for call in bot.media_calls] == [10, 10, 5]
    assert bot.message_calls == []


def test_send_chunks_stops_on_api_error():
    bot = FailingBot()
    media: list[Any] = [object() for _ in range(15)]
    asyncio.run(send_media_chunks(bot, 1, 2, media))
    assert len(bot.media_calls) == 1
    assert len(bot.message_calls) == 1
    assert 'Failed to send media group' in bot.message_calls[0]['text']


def test_build_post_contents_drops_video_thumbnails(tmp_path):
    (tmp_path / '01.jpg').write_bytes(b'x')
    (tmp_path / '02.mp4').write_bytes(b'x')
    (tmp_path / '02.jpg').write_bytes(b'x')  # video thumbnail: dropped
    (tmp_path / '03.jpg').write_bytes(b'x')
    media = build_post_contents_from_dir(tmp_path, 'caption')
    assert [type(m).__name__ for m in media] == [
        'InputMediaPhoto',
        'InputMediaVideo',
        'InputMediaPhoto',
    ]
    assert media[0].caption == 'caption'
    assert media[1].caption is None


def test_build_post_contents_truncates_long_caption(tmp_path):
    (tmp_path / '01.jpg').write_bytes(b'x')
    media = build_post_contents_from_dir(tmp_path, 'x' * 2000)
    assert media[0].caption is not None
    assert len(media[0].caption) == 1024
    assert media[0].caption.endswith('...')


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t


def test_rate_limiter_allows_until_limit():
    clock = Clock()
    limiter = RateLimiter(2, 10.0, now=clock.now)
    assert limiter.allow(1)
    assert limiter.allow(1)
    assert not limiter.allow(1)


def test_rate_limiter_keys_are_independent():
    clock = Clock()
    limiter = RateLimiter(1, 10.0, now=clock.now)
    assert limiter.allow(1)
    assert limiter.allow(2)
    assert not limiter.allow(1)


def test_rate_limiter_window_expires():
    clock = Clock()
    limiter = RateLimiter(1, 10.0, now=clock.now)
    assert limiter.allow(1)
    assert not limiter.allow(1)
    clock.t = 10.0
    assert limiter.allow(1)
