"""Tests for run_id format validation (§10.7, v4.2 fix #3)."""

import re
import pytest

RUN_ID_RE = re.compile(r"^[a-f0-9]{8}$")


class TestRunIdValidation:
    def test_valid_run_id(self):
        assert RUN_ID_RE.match("a1b2c3d4")

    def test_valid_all_hex(self):
        assert RUN_ID_RE.match("deadbeef")

    def test_reject_too_short(self):
        assert not RUN_ID_RE.match("a1b2c3")

    def test_reject_too_long(self):
        assert not RUN_ID_RE.match("a1b2c3d4e5")

    def test_reject_uppercase(self):
        assert not RUN_ID_RE.match("A1B2C3D4")

    def test_reject_non_hex(self):
        assert not RUN_ID_RE.match("ghijklmn")

    def test_reject_path_traversal_encoded(self):
        assert not RUN_ID_RE.match("..%5C..%5")

    def test_reject_path_traversal_backslash(self):
        assert not RUN_ID_RE.match("..\\..\\se")

    def test_reject_empty(self):
        assert not RUN_ID_RE.match("")

    def test_reject_spaces(self):
        assert not RUN_ID_RE.match("a1b2 c3d")
