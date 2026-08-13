"""Unit tests for config loading: parsing, env overrides, error messages."""

import pytest

from config import load_config


def write_config(tmp_path, content: str):
    path = tmp_path / 'config.toml'
    path.write_text(content)
    return path


BASIC = (
    'bot_token = "123:abc"\n'
    'instagram_username = "user"\n'
    '[whitelist]\n'
    'users = ["1", 2]\n'
    'groups = ["-100"]\n'
)


def test_load_basic(tmp_path):
    path = write_config(tmp_path, BASIC)
    cfg = load_config(path)
    assert cfg.bot_token == '123:abc'
    assert cfg.instagram_username == 'user'
    assert cfg.whitelist_users == (1, 2)
    assert cfg.whitelist_groups == (-100,)


def test_env_override(tmp_path, monkeypatch):
    path = write_config(
        tmp_path,
        'bot_token = "123:abc"\n'
        'instagram_username = "user"\n'
        '[whitelist]\n'
        'users = []\n'
        'groups = []\n',
    )
    monkeypatch.setenv('BOT_TOKEN', 'env:token')
    monkeypatch.setenv('INSTAGRAM_USERNAME', 'env-user')
    cfg = load_config(path)
    assert cfg.bot_token == 'env:token'
    assert cfg.instagram_username == 'env-user'


def test_missing_file_gives_bootstrap_hint(tmp_path):
    with pytest.raises(RuntimeError, match='config.example.toml'):
        load_config(tmp_path / 'nope.toml')


def test_missing_token_raises(tmp_path):
    path = write_config(
        tmp_path,
        'instagram_username = "user"\n[whitelist]\nusers = []\ngroups = []\n',
    )
    with pytest.raises(RuntimeError, match='bot_token'):
        load_config(path)


def test_bad_whitelist_type_raises(tmp_path):
    path = write_config(
        tmp_path,
        'bot_token = "123:abc"\n'
        'instagram_username = "user"\n'
        '[whitelist]\n'
        'users = "not-a-list"\n'
        'groups = []\n',
    )
    with pytest.raises(TypeError, match='whitelist.users'):
        load_config(path)


def test_download_mode_defaults_false(tmp_path):
    path = write_config(tmp_path, BASIC)
    assert load_config(path).download_mode is False


def test_download_mode_true(tmp_path):
    path = write_config(tmp_path, 'download_mode = true\n' + BASIC)
    assert load_config(path).download_mode is True


def test_download_mode_non_bool_raises(tmp_path):
    path = write_config(tmp_path, 'download_mode = "yes"\n' + BASIC)
    with pytest.raises(TypeError, match='download_mode'):
        load_config(path)
