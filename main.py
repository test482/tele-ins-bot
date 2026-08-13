"""Telegram bot entry point: forwards Instagram posts to whitelisted chats."""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

import instaloader
import telebot
import telebot.types
from instaloader.exceptions import LoginRequiredException
from loguru import logger
from platformdirs import user_runtime_path
from telebot.async_telebot import AsyncTeleBot

import utils
from config import load_config
from filters import IsFromWhitelist
from utils import RateLimiter, truncate_caption

INSTAGRAM_URL_RE = re.compile(
    r'https?://(?:www\.|m\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)',
    re.IGNORECASE,
)

RATE_LIMIT_MAX = 10  # requests per window
RATE_LIMIT_WINDOW_SECONDS = 60.0


def extract_shortcodes(text: str | None) -> list[str]:
    """Extract unique Instagram shortcodes from message text, preserving order."""
    if not text:
        return []
    return list(dict.fromkeys(INSTAGRAM_URL_RE.findall(text)))


def display_name(user) -> str:
    parts = [user.first_name, user.last_name]
    if user.username:
        parts.append(f'@{user.username}')
    return ' '.join(filter(None, parts))


def _reload_session(L, username: str) -> bool:
    """Try to reload the saved Instagram session; True on success."""
    try:
        L.load_session_from_file(username=username)
        logger.info('Reloaded Instagram session for {}', username)
        return True
    except Exception as e:  # noqa: BLE001 - any session problem is non-fatal
        logger.exception('Failed to reload Instagram session for {}: {}', username, e)
        return False


def _post_from_shortcode(L, shortcode: str, username: str):
    """Fetch a post; on login-required, reload the session once and retry."""
    try:
        return instaloader.Post.from_shortcode(L.context, shortcode)
    except LoginRequiredException:
        if _reload_session(L, username):
            return instaloader.Post.from_shortcode(L.context, shortcode)
        raise


async def main() -> None:
    cfg = load_config()

    try:
        bot = AsyncTeleBot(token=cfg.bot_token)
    except Exception as e:  # noqa: BLE001 - never let an init failure take down the bot
        logger.error('Failed to initialize bot: {}', e)
        return

    L = instaloader.Instaloader()
    try:
        L.load_session_from_file(username=cfg.instagram_username)
    except Exception as e:  # noqa: BLE001 - any session problem is non-fatal
        logger.error('Failed to load Instagram session: {}', e)
        return

    limiter = RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_SECONDS)

    @bot.message_handler(commands=['help'])
    async def send_welcome(message):
        await bot.reply_to(
            message=message,
            text="Private bot. send me an instagram post link, I'll fetch it for you.",
        )

    @bot.message_handler(commands=['uid'])
    async def uid(message):
        if message.from_user is None:
            return
        await bot.reply_to(
            message=message,
            text=f'Your user ID is `{message.from_user.id}`',
            parse_mode='MarkdownV2',
        )

    @bot.message_handler(is_from_whitelist=True)
    async def handle_instagram_url(message):
        shortcodes = extract_shortcodes(message.text)
        if not shortcodes:
            return

        user = message.from_user
        logger.info('Request from {} ({}): {}', user.id, display_name(user), shortcodes)

        if not limiter.allow(user.id):
            logger.warning('Rate limited user {} ({})', user.id, display_name(user))
            await bot.reply_to(
                message,
                'You are sending too many requests. Please wait a minute and try again.',
            )
            return

        for shortcode in shortcodes:
            logger.info('Fetching shortcode: {}', shortcode)
            try:
                post = _post_from_shortcode(L, shortcode, cfg.instagram_username)
            except LoginRequiredException:
                logger.error('Instagram session expired or login required')
                await bot.reply_to(
                    message=message,
                    text='Instagram session expired. Please reload the session.',
                )
                return
            except Exception as e:  # noqa: BLE001 - report, never drop the request
                logger.exception('Failed to fetch post: {}', e)
                await bot.reply_to(
                    message=message,
                    text=f'Failed to fetch post: {e}',
                )
                continue

            if cfg.download_mode:
                await _handle_download_mode(
                    bot, message, L, post, cfg.instagram_username
                )
            else:
                await _handle_url_mode(bot, message, post)

    bot.add_custom_filter(
        IsFromWhitelist(bot, cfg.whitelist_users, cfg.whitelist_groups)
    )
    await bot.polling()


async def _download_post_files(L, post, username: str, tmpdir) -> None:
    """Run Instaloader's download in a thread; reload session once if needed."""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: L.download_post(post, target=tmpdir))
    except LoginRequiredException:
        if _reload_session(L, username):
            await loop.run_in_executor(
                None, lambda: L.download_post(post, target=tmpdir)
            )
        else:
            raise


async def _handle_download_mode(bot, message, L, post, username: str):
    """Download post files locally then upload to Telegram."""
    runtime_base = user_runtime_path(appname='tgbot')
    runtime_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime_base) as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        logger.info('Downloading {} to {}', post.shortcode, tmpdir)
        try:
            await _download_post_files(L, post, username, tmpdir)
            post_contents = utils.build_post_contents_from_dir(tmpdir, post.caption)
            await utils.send_media_chunks(bot, message.chat.id, message.id, post_contents)
        except LoginRequiredException:
            logger.error('Instagram session expired or login required')
            await bot.reply_to(
                message=message,
                text='Instagram session expired. Please reload the session.',
            )
        except Exception as e:  # noqa: BLE001 - report, never drop the request
            logger.exception('Failed to download post: {}', e)
            await bot.reply_to(message, f'Failed to download post: {e}')
        finally:
            logger.info('Cleaned up {}', tmpdir)


async def _handle_url_mode(bot, message, post):
    """Build InputMedia list from CDN URLs and send directly."""
    post_contents: list[telebot.types.InputMedia] = []
    caption = truncate_caption(post.caption)
    match post.typename:
        case 'GraphImage':
            post_contents.append(
                telebot.types.InputMediaPhoto(media=post.url, caption=caption)
            )
            logger.info('GraphImage: {}', post.url)
        case 'GraphVideo':
            if post.video_url is not None:
                post_contents.append(
                    telebot.types.InputMediaVideo(media=post.video_url, caption=caption)
                )
                logger.info('GraphVideo: {}', post.video_url)
            else:
                logger.error('Detected GraphVideo post but video_url is None')
                await bot.reply_to(
                    message=message,
                    text='Detected GraphVideo post but video_url is None',
                )
                return
        case 'GraphSidecar':
            first = True
            for node in post.get_sidecar_nodes():
                if node.is_video:
                    post_contents.append(
                        telebot.types.InputMediaVideo(
                            media=node.video_url,
                            caption=caption if first else None,
                        )
                    )
                else:
                    post_contents.append(
                        telebot.types.InputMediaPhoto(
                            media=node.display_url,
                            caption=caption if first else None,
                        )
                    )
                first = False
            logger.info('GraphSidecar: {} items', len(post_contents))
        case _:
            logger.error('Unknown post type: {}', post.typename)
            await bot.reply_to(
                message=message,
                text=f'Unknown post type: {post.typename}',
            )
            return
    await utils.send_media_chunks(bot, message.chat.id, message.id, post_contents)


if __name__ == '__main__':
    asyncio.run(main())
