from pathlib import Path

import telebot
import telebot.apihelper
import telebot.types
from loguru import logger
from telebot.async_telebot import AsyncTeleBot

from config import MAX_MEDIA_NUM_PER_MESSAGE


def chunk_list(items, size):
    """chunk a list into size-sized pieces"""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_post_contents_from_dir(
    directory: Path, caption: str | None
) -> list[telebot.types.InputMedia]:
    """Build InputMedia list from files downloaded by Instaloader.

    Instaloader saves a .jpg thumbnail alongside each .mp4 video. We keep all
    .mp4 files and only .jpg files that have no corresponding .mp4 (i.e. not
    thumbnails). Files are sorted by name to preserve sidecar order.
    """
    mp4_stems = {f.stem for f in directory.iterdir() if f.suffix == ".mp4"}
    media_files = sorted(
        f
        for f in directory.iterdir()
        if f.suffix == ".mp4" or (f.suffix == ".jpg" and f.stem not in mp4_stems)
    )
    post_contents: list[telebot.types.InputMedia] = []
    for i, f in enumerate(media_files):
        cap = caption if i == 0 else None
        if f.suffix == ".mp4":
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
    bot: AsyncTeleBot, chat_id, reply_to_message_id, media_list
):
    """
    send media in chunks to avoid exceeding Telegram's limit
    """
    for chunk in chunk_list(media_list, MAX_MEDIA_NUM_PER_MESSAGE):
        try:
            await bot.send_media_group(
                chat_id=chat_id,
                reply_parameters=telebot.types.ReplyParameters(
                    message_id=reply_to_message_id
                ),
                disable_notification=True,
                media=chunk,
            )
        except telebot.apihelper.ApiException as e:
            logger.exception(f"Failed to send media group: {e}")
            await bot.send_message(
                chat_id,
                "Failed to send media group: " + str(e),
                reply_to_message_id=reply_to_message_id,
            )
            return
