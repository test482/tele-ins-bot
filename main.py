import asyncio
import re

from platformdirs import user_runtime_path

import instaloader
import telebot
import telebot.types
from loguru import logger
from telebot.async_telebot import AsyncTeleBot

import utils
from config import BOT_TOKEN, DOWNLOAD_MODE, INSTAGRAM_USERNAME
from filters import isFromWhiteList

INSTAGRAM_URL_RE = re.compile(
    r"https://www\.instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)"
)


async def main():
    try:
        bot = AsyncTeleBot(token=BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        return

    L = instaloader.Instaloader()
    try:
        L.load_session_from_file(username=INSTAGRAM_USERNAME)
    except Exception as e:
        logger.error(f"Failed to load Instagram session: {e}")
        return

    @bot.message_handler(commands=["help"])
    async def send_welcome(message):
        await bot.reply_to(
            message=message,
            text="Private bot. send me an instagram post link, I'll fetch it for you.",
        )

    @bot.message_handler(commands=["uid"])
    async def uid(message):
        await bot.reply_to(
            message=message,
            text=f"Your user ID is `{message.from_user.id}`",
            parse_mode="MarkdownV2",
        )

    @bot.message_handler(is_from_white_list=True)
    async def handle_instagram_url(message):
        shortcodes = INSTAGRAM_URL_RE.findall(message.text)
        if not shortcodes:
            return

        user = message.from_user
        display_name = " ".join(
            filter(
                None,
                [
                    user.first_name,
                    user.last_name,
                    f"@{user.username}" if user.username else None,
                ],
            )
        )
        logger.info(f"Request from {user.id} ({display_name}): {shortcodes}")

        for shortcode in shortcodes:
            logger.info(f"Fetching shortcode: {shortcode}")
            try:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
            except instaloader.exceptions.LoginRequiredException:
                logger.error("Instagram session expired or login required")
                await bot.reply_to(
                    message=message,
                    text="Instagram session expired. Please reload the session.",
                )
                return
            except Exception as e:
                logger.exception(f"Failed to fetch post: {e}")
                await bot.reply_to(
                    message=message,
                    text=f"Failed to fetch post: {e}",
                )
                continue

            if DOWNLOAD_MODE:
                await _handle_download_mode(bot, message, L, post)
            else:
                await _handle_url_mode(bot, message, post)

    bot.add_custom_filter(isFromWhiteList(bot))
    await bot.polling()


async def _handle_download_mode(bot, message, L, post):
    """Download post files locally then upload to Telegram."""
    tmpdir = user_runtime_path(appname="tgbot") / post.shortcode
    tmpdir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {post.shortcode} to {tmpdir}")
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: L.download_post(post, target=tmpdir))
        post_contents = utils.build_post_contents_from_dir(tmpdir, post.caption)
        await utils.send_media_chunks(bot, message.chat.id, message.id, post_contents)
    finally:
        for f in tmpdir.iterdir():
            f.unlink(missing_ok=True)
        tmpdir.rmdir()
        logger.info(f"Cleaned up {tmpdir}")


async def _handle_url_mode(bot, message, post):
    """Build InputMedia list from CDN URLs and send directly."""
    post_contents: list[telebot.types.InputMedia] = []
    match post.typename:
        case "GraphImage":
            post_contents.append(
                telebot.types.InputMediaPhoto(media=post.url, caption=post.caption)
            )
            logger.info(f"GraphImage: {post.url}")
        case "GraphVideo":
            if post.video_url is not None:
                post_contents.append(
                    telebot.types.InputMediaVideo(
                        media=post.video_url, caption=post.caption
                    )
                )
                logger.info(f"GraphVideo: {post.video_url}")
            else:
                logger.error("Detected GraphVideo post but video_url is None")
                await bot.reply_to(
                    message=message,
                    text="Detected GraphVideo post but video_url is None",
                )
                return
        case "GraphSidecar":
            first = True
            for node in post.get_sidecar_nodes():
                if node.is_video:
                    post_contents.append(
                        telebot.types.InputMediaVideo(
                            media=node.video_url,
                            caption=post.caption if first else None,
                        )
                    )
                else:
                    post_contents.append(
                        telebot.types.InputMediaPhoto(
                            media=node.display_url,
                            caption=post.caption if first else None,
                        )
                    )
                first = False
            logger.info(f"GraphSidecar: {len(post_contents)} items")
        case _:
            logger.error(f"Unknown post type: {post.typename}")
            await bot.reply_to(
                message=message,
                text=f"Unknown post type: {post.typename}",
            )
            return
    await utils.send_media_chunks(bot, message.chat.id, message.id, post_contents)


if __name__ == "__main__":
    asyncio.run(main())
