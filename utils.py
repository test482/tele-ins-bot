"""Shared helpers: media chunking, caption handling, rate limiting."""

from __future__ import annotations

import itertools
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

import telebot.apihelper
import telebot.types
from loguru import logger

MAX_MEDIA_PER_MESSAGE = 10  # Telegram hard limit for media groups
CAPTION_LIMIT = 1024  # Telegram hard limit for captions


def truncate_caption(caption: str | None) -> str | None:
    """Truncate a caption to Telegram's limit, keeping an ellipsis tail."""
    if caption is None:
        return None
    if len(caption) <= CAPTION_LIMIT:
        return caption
    return caption[: CAPTION_LIMIT - 3] + '...'


def build_post_contents_from_dir(
    directory: Path, caption: str | None
) -> list[telebot.types.InputMedia]:
    """Build InputMedia list from files downloaded by Instaloader.

    Instaloader saves a .jpg thumbnail alongside each .mp4 video. We keep all
    .mp4 files and only .jpg files that have no corresponding .mp4 (i.e. not
    thumbnails). Files are sorted by name to preserve sidecar order.
    """
    mp4_stems = {f.stem for f in directory.iterdir() if f.suffix == '.mp4'}
    media_files = sorted(
        f
        for f in directory.iterdir()
        if f.suffix == '.mp4' or (f.suffix == '.jpg' and f.stem not in mp4_stems)
    )
    post_contents: list[telebot.types.InputMedia] = []
    for i, f in enumerate(media_files):
        cap = truncate_caption(caption) if i == 0 else None
        if f.suffix == '.mp4':
            post_contents.append(
                telebot.types.InputMediaVideo(
                    media=telebot.types.InputFile(f), caption=cap
                )
            )
        else:
            post_contents.append(
                telebot.types.InputMediaPhoto(
                    media=telebot.types.InputFile(f), caption=cap
                )
            )
    return post_contents


async def send_media_chunks(
    bot: Any,
    chat_id: int,
    reply_to_message_id: int,
    media_list: list[telebot.types.InputMedia],
) -> None:
    """Send media in chunks of MAX_MEDIA_PER_MESSAGE; stop on first API error."""
    for chunk in itertools.batched(media_list, MAX_MEDIA_PER_MESSAGE):
        try:
            await bot.send_media_group(
                chat_id=chat_id,
                reply_parameters=telebot.types.ReplyParameters(
                    message_id=reply_to_message_id
                ),
                disable_notification=True,
                media=list(chunk),
            )
        except telebot.apihelper.ApiException as e:
            logger.exception('Failed to send media group: {}', e)
            await bot.send_message(
                chat_id,
                'Failed to send media group: ' + str(e),
                reply_parameters=telebot.types.ReplyParameters(
                    message_id=reply_to_message_id
                ),
            )
            return


class RateLimiter:
    """Sliding-window rate limiter keyed by an integer (e.g. user id)."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._now = now
        self._hits: dict[int, deque[float]] = {}

    def allow(self, key: int) -> bool:
        now = self._now()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._max_requests:
            return False
        hits.append(now)
        return True
