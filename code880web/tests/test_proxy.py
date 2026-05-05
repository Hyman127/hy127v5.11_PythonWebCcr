"""Tests for Hub proxy helpers."""

from code880web.hub.proxy import _first_cookie


def test_first_cookie_prefers_hy127_session():
    cookies = {"hy127_session": "new", "code880_session": "old"}
    assert _first_cookie(cookies) == "new"


def test_first_cookie_accepts_legacy_code880_session():
    cookies = {"code880_session": "old"}
    assert _first_cookie(cookies) == "old"


def test_first_cookie_returns_empty_when_missing():
    assert _first_cookie({}) == ""
