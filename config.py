import tomllib
from pathlib import Path

MAX_MEDIA_NUM_PER_MESSAGE = 10

with open(Path(__file__).parent / "config.toml", "rb") as f:
    config = tomllib.load(f)

BOT_TOKEN: str = config["bot_token"]
INSTAGRAM_USERNAME: str = config["instagram_username"]
DOWNLOAD_MODE: bool = config.get("download_mode", False)
WHITELIST_USERS: list[int] = [int(uid) for uid in config["whitelist"]["users"]]
WHITELIST_GROUPS: list[int] = [int(gid) for gid in config["whitelist"]["groups"]]
