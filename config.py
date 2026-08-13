"""Typed configuration loading with environment-variable overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / 'config.toml'


@dataclass(frozen=True)
class Config:
    bot_token: str
    instagram_username: str
    download_mode: bool
    whitelist_users: tuple[int, ...]
    whitelist_groups: tuple[int, ...]


def _int_list(name: str, values: object) -> tuple[int, ...]:
    if not isinstance(values, list):
        raise TypeError(f"config: '{name}' must be a list of ids")
    return tuple(int(v) for v in values)


def _required_str(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"config: '{name}' is missing or empty")
    return value


@lru_cache(maxsize=1)
def load_config(path: Path | None = None) -> Config:
    """Load the TOML config; environment variables override file values."""
    cfg_path = path or CONFIG_PATH
    try:
        with open(cfg_path, 'rb') as f:
            raw = tomllib.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f'Config file not found: {cfg_path}\n'
            'Copy config.example.toml to config.toml and fill in your values.'
        ) from None

    bot_token = os.environ.get('BOT_TOKEN') or raw.get('bot_token')
    instagram_username = os.environ.get('INSTAGRAM_USERNAME') or raw.get(
        'instagram_username'
    )

    whitelist = raw.get('whitelist', {})
    if not isinstance(whitelist, dict):
        raise TypeError("config: 'whitelist' must be a table")

    download_mode = raw.get('download_mode', False)
    if not isinstance(download_mode, bool):
        raise TypeError("config: 'download_mode' must be a boolean")

    return Config(
        bot_token=_required_str('bot_token', bot_token),
        instagram_username=_required_str('instagram_username', instagram_username),
        download_mode=download_mode,
        whitelist_users=_int_list('whitelist.users', whitelist.get('users', [])),
        whitelist_groups=_int_list('whitelist.groups', whitelist.get('groups', [])),
    )
