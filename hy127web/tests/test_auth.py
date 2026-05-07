"""Tests for authentication, CSRF, and Origin validation (§4, §12 of spec)."""

import os
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from hy127web.hub.auth import AuthManager
from hy127web.hub.app import app, hub_config


@pytest.fixture
def auth_mgr(tmp_path):
    keys_dir = str(tmp_path / "keys")
    return AuthManager(keys_dir, hub_port=8800)


class TestLaunchToken:
    def test_token_written_to_file(self, auth_mgr, tmp_path):
        token_path = os.path.join(str(tmp_path / "keys"), "launch_token")
        assert os.path.isfile(token_path)
        with open(token_path) as f:
            assert f.read() == auth_mgr.launch_token

    def test_verify_valid_token(self, auth_mgr):
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {auth_mgr.launch_token}"}
        assert auth_mgr.verify_launch_token(request) is True

    def test_reject_invalid_token(self, auth_mgr):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer wrong_token"}
        assert auth_mgr.verify_launch_token(request) is False

    def test_reject_no_header(self, auth_mgr):
        request = MagicMock()
        request.headers = {}
        assert auth_mgr.verify_launch_token(request) is False


class TestBootstrap:
    def test_create_and_use_code(self, auth_mgr):
        code = auth_mgr.create_bootstrap_code("/w/test")
        response = auth_mgr.handle_bootstrap(code)
        assert response.status_code == 302

    def test_reject_reuse(self, auth_mgr):
        code = auth_mgr.create_bootstrap_code("/w/test")
        auth_mgr.handle_bootstrap(code)
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            auth_mgr.handle_bootstrap(code)

    def test_reject_invalid_code(self, auth_mgr):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            auth_mgr.handle_bootstrap("nonexistent_code")


class TestSession:
    def test_valid_session(self, auth_mgr):
        code = auth_mgr.create_bootstrap_code("/")
        auth_mgr.handle_bootstrap(code)
        session_id = list(auth_mgr._sessions.keys())[0]
        assert auth_mgr.verify_session(session_id) is True

    def test_invalid_session(self, auth_mgr):
        assert auth_mgr.verify_session("fake_session_id") is False


class TestOriginCheck:
    def test_exact_port_match(self, auth_mgr):
        request = MagicMock()
        code = auth_mgr.create_bootstrap_code("/")
        auth_mgr.handle_bootstrap(code)
        session_id = list(auth_mgr._sessions.keys())[0]
        csrf = auth_mgr._sessions[session_id]["csrf"]
        request.cookies = {"code880_session": session_id, "code880_csrf": csrf}
        request.headers = {"X-Code880-CSRF": csrf, "Origin": "http://127.0.0.1:8800"}
        auth_mgr.require_csrf(request)  # should not raise

    def test_reject_different_port(self, auth_mgr):
        request = MagicMock()
        code = auth_mgr.create_bootstrap_code("/")
        auth_mgr.handle_bootstrap(code)
        session_id = list(auth_mgr._sessions.keys())[0]
        csrf = auth_mgr._sessions[session_id]["csrf"]
        request.cookies = {"code880_session": session_id, "code880_csrf": csrf}
        request.headers = {"X-Code880-CSRF": csrf, "Origin": "http://127.0.0.1:9999"}
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_mgr.require_csrf(request)
        assert exc_info.value.status_code == 403

    def test_reject_external_origin(self, auth_mgr):
        request = MagicMock()
        code = auth_mgr.create_bootstrap_code("/")
        auth_mgr.handle_bootstrap(code)
        session_id = list(auth_mgr._sessions.keys())[0]
        csrf = auth_mgr._sessions[session_id]["csrf"]
        request.cookies = {"code880_session": session_id, "code880_csrf": csrf}
        request.headers = {"X-Code880-CSRF": csrf, "Origin": "http://evil.com"}
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            auth_mgr.require_csrf(request)

    def test_no_origin_header_passes(self, auth_mgr):
        request = MagicMock()
        code = auth_mgr.create_bootstrap_code("/")
        auth_mgr.handle_bootstrap(code)
        session_id = list(auth_mgr._sessions.keys())[0]
        csrf = auth_mgr._sessions[session_id]["csrf"]
        request.cookies = {"code880_session": session_id, "code880_csrf": csrf}
        request.headers = {"X-Code880-CSRF": csrf}
        auth_mgr.require_csrf(request)  # no Origin header = same-origin, should pass

    def test_hy127_cookie_and_header_passes(self, auth_mgr):
        request = MagicMock()
        code = auth_mgr.create_bootstrap_code("/")
        auth_mgr.handle_bootstrap(code)
        session_id = list(auth_mgr._sessions.keys())[0]
        csrf = auth_mgr._sessions[session_id]["csrf"]
        request.cookies = {"hy127_session": session_id, "hy127_csrf": csrf}
        request.headers = {"X-Hy127-CSRF": csrf, "Origin": "http://127.0.0.1:8800"}
        auth_mgr.require_csrf(request)


@pytest.fixture
def hub_client(monkeypatch):
    monkeypatch.setattr(hub_config, "port", 8800)
    return TestClient(app, raise_server_exceptions=False)


class TestCorsMiddleware:
    def test_preflight_allows_exact_origin(self, hub_client):
        response = hub_client.options(
            "/api/hub/identity",
            headers={
                "Origin": "http://127.0.0.1:8800",
                "Access-Control-Request-Headers": "X-Code880-CSRF",
            },
        )
        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:8800"

    def test_preflight_rejects_other_localhost_port(self, hub_client):
        response = hub_client.options(
            "/api/hub/identity",
            headers={"Origin": "http://127.0.0.1:9999"},
        )
        assert response.status_code == 403
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_get_does_not_grant_other_origin(self, hub_client):
        response = hub_client.get(
            "/api/hub/identity",
            headers={"Origin": "http://127.0.0.1:9999"},
        )
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers
