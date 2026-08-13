"""Unit tests for Instagram URL parsing and shortcode extraction."""

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
