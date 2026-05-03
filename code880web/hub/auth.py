import os
import secrets
import time
from dataclasses import dataclass, field

from fastapi import Request, HTTPException, Response
from starlette.responses import RedirectResponse


@dataclass
class BootstrapCode:
    code: str
    target: str
    created_at: float
    used: bool = False


class AuthManager:
    SESSION_TTL = 86400 * 7  # 7 days
    BOOTSTRAP_TTL = 60       # 60 seconds

    def __init__(self, keys_dir: str, hub_port: int = 0):
        self.keys_dir = keys_dir
        self.hub_port = hub_port
        os.makedirs(keys_dir, exist_ok=True)

        self.launch_token = secrets.token_hex(32)
        self.launch_token_path = self._write_launch_token()

        self._sessions: dict[str, dict] = {}
        self._bootstrap_codes: dict[str, BootstrapCode] = {}

    def _write_launch_token(self) -> str:
        token_paths = [
            os.path.join(self.keys_dir, "launch_token"),
            os.path.join(
                self.keys_dir,
                f"launch_token_{os.getpid()}_{secrets.token_hex(4)}",
            ),
        ]
        last_error: OSError | None = None
        for token_path in token_paths:
            try:
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(self.launch_token)
                return token_path
            except OSError as exc:
                last_error = exc
        raise last_error or OSError("failed to write launch token")

    def verify_launch_token(self, request: Request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return auth[7:] == self.launch_token

    def require_launch_token(self, request: Request):
        if not self.verify_launch_token(request):
            raise HTTPException(403, "launch_token 无效")

    def create_bootstrap_code(self, target: str) -> str:
        code = secrets.token_urlsafe(32)
        self._bootstrap_codes[code] = BootstrapCode(
            code=code, target=target, created_at=time.time()
        )
        return code

    def handle_bootstrap(self, code: str) -> Response:
        bc = self._bootstrap_codes.get(code)
        if not bc:
            raise HTTPException(400, "无效的认证码")
        if bc.used:
            raise HTTPException(400, "认证码已使用")
        if time.time() - bc.created_at > self.BOOTSTRAP_TTL:
            self._bootstrap_codes.pop(code, None)
            raise HTTPException(400, "认证码已过期")

        bc.used = True

        session_id = secrets.token_hex(32)
        csrf_token = secrets.token_hex(16)
        self._sessions[session_id] = {
            "csrf": csrf_token,
            "created_at": time.time(),
        }

        response = RedirectResponse(url=bc.target, status_code=302)
        response.set_cookie(
            "code880_session", session_id,
            httponly=True, samesite="strict", path="/"
        )
        response.set_cookie(
            "code880_csrf", csrf_token,
            httponly=False, samesite="strict", path="/"
        )
        return response

    def verify_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        if time.time() - session["created_at"] > self.SESSION_TTL:
            self._sessions.pop(session_id, None)
            return False
        return True

    def require_session(self, request: Request):
        session_id = request.cookies.get("code880_session")
        if not session_id or not self.verify_session(session_id):
            raise HTTPException(401, "会话无效")

    @property
    def _allowed_origin(self) -> str:
        return f"http://127.0.0.1:{self.hub_port}"

    def _check_origin(self, request: Request):
        origin = request.headers.get("Origin")
        if not origin:
            return
        if origin != self._allowed_origin:
            raise HTTPException(403, "来源不合法")

    def require_csrf(self, request: Request):
        self.require_session(request)
        csrf_cookie = request.cookies.get("code880_csrf")
        csrf_header = request.headers.get("X-Code880-CSRF")
        if not csrf_cookie or not csrf_header:
            raise HTTPException(403, "缺少 CSRF 凭证")
        if csrf_cookie != csrf_header:
            raise HTTPException(403, "CSRF 验证失败")
        self._check_origin(request)

    def cleanup_expired(self):
        now = time.time()
        expired_sessions = [
            k for k, v in self._sessions.items()
            if now - v["created_at"] > self.SESSION_TTL
        ]
        for k in expired_sessions:
            del self._sessions[k]
        expired_codes = [
            k for k, v in self._bootstrap_codes.items()
            if now - v.created_at > self.BOOTSTRAP_TTL
        ]
        for k in expired_codes:
            del self._bootstrap_codes[k]
