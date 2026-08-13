"""Unit tests for Instagram URL parsing and shortcode extraction."""

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from main import extract_shortcodes


def test_none_and_empty_text():
    assert extract_shortcodes(None) == []
    assert extract_shortcodes('') == []
    assert extract_shortcodes('no links here') == []


def test_various_url_forms():
    text = (
        'https://www.instagram.com/p/AbC123_/ '
        'http://instagram.com/reel/xYz-45 '
        'https://m.instagram.com/tv/zzz_AAA '
        'https://www.instagram.com/reel/abc?igsh=xyz'
    )
    assert extract_shortcodes(text) == ['AbC123_', 'xYz-45', 'zzz_AAA', 'abc']


def test_ignores_other_domains():
    assert extract_shortcodes('https://example.com/p/AbC123_') == []


def test_dedup_preserves_order():
    text = (
        'https://www.instagram.com/p/X '
        'https://www.instagram.com/p/X '
        'https://instagram.com/reel/Y '
        'https://www.instagram.com/p/X'
    )
    assert extract_shortcodes(text) == ['X', 'Y']


def test_concurrent_downloads_use_isolated_directories():
    """Regression test: concurrent requests for same shortcode don't collide."""
    from main import _handle_download_mode
    import asyncio

    # Track directories created during concurrent invocations
    created_dirs = []

    original_temp_dir = tempfile.TemporaryDirectory

    class TrackedTemporaryDirectory:
        def __init__(self, *args, **kwargs):
            self._inner = original_temp_dir(*args, **kwargs)
            self.name = self._inner.name
            created_dirs.append(self.name)

        def __enter__(self):
            return self._inner.__enter__()

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

    async def run_test():
        # Mock dependencies
        mock_bot = MagicMock()
        mock_message = MagicMock()
        mock_message.chat.id = 123
        mock_message.id = 456
        mock_L = MagicMock()
        mock_post = MagicMock()
        mock_post.shortcode = 'SAME_SHORTCODE'
        mock_post.caption = 'test'

        with (
            patch('tempfile.TemporaryDirectory', TrackedTemporaryDirectory),
            patch('main._download_post_files', new=AsyncMock(return_value=None)),
            patch('main.utils.build_post_contents_from_dir', return_value=[]),
            patch('main.utils.send_media_chunks', new=AsyncMock(return_value=None)),
        ):
            # Simulate two concurrent requests for the same shortcode
            await asyncio.gather(
                _handle_download_mode(mock_bot, mock_message, mock_L, mock_post, 'user'),
                _handle_download_mode(mock_bot, mock_message, mock_L, mock_post, 'user'),
            )

        # Assert: two different directories were created (no collision)
        assert len(created_dirs) == 2
        assert created_dirs[0] != created_dirs[1], \
            'Concurrent requests for same shortcode should use different temp directories'

    asyncio.run(run_test())
