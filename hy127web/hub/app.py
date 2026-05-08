import json
import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .ai_runtime import DirectHttpRuntime
from .auth import AuthManager
from .config import HubConfig, find_available_port, get_global_dir
from .models_manager import ModelsManager
from .proxy import proxy_http_to_worker, proxy_ws_to_worker
from .registry import ProjectRegistry
from .subagent_manager import SubAgentManager
from .supervisor import WorkerSupervisor

logger = logging.getLogger("hub")

hub_config = HubConfig()
auth: AuthManager | None = None
registry: ProjectRegistry | None = None
supervisor: WorkerSupervisor | None = None
models_mgr: ModelsManager | None = None
subagent_mgr: SubAgentManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global auth, registry, supervisor, models_mgr, subagent_mgr, hub_config

    # port must already be set by main() before uvicorn starts;
    # lifespan must not re-probe, or it would diverge from uvicorn's listen port
    if hub_config.port == 0:
        raise RuntimeError("hub_config.port 未设置，必须在启动前通过 main() 设定")

    global_dir = hub_config.global_dir
    os.makedirs(global_dir, exist_ok=True)
    os.makedirs(hub_config.log_dir, exist_ok=True)

    log_handlers = [logging.StreamHandler()]
    log_path = os.path.join(hub_config.log_dir, "hub.log")
    try:
        log_handlers.insert(0, logging.FileHandler(log_path, encoding="utf-8"))
    except OSError:
        fallback_log = os.path.join(hub_config.log_dir, f"hub_{os.getpid()}.log")
        try:
            log_handlers.insert(0, logging.FileHandler(fallback_log, encoding="utf-8"))
        except OSError:
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=log_handlers,
    )

    auth = AuthManager(hub_config.keys_dir, hub_port=hub_config.port)
    registry = ProjectRegistry(hub_config.db_path)
    supervisor = WorkerSupervisor(hub_config)
    models_mgr = ModelsManager(hub_config.models_path, hub_config.keys_dir)
    subagent_mgr = SubAgentManager(models_mgr)

    runtime_path = hub_config.runtime_path
    with open(runtime_path, "w", encoding="utf-8") as f:
        json.dump({
            "pid": os.getpid(),
            "port": hub_config.port,
            "base_url": hub_config.base_url,
            "launch_token_path": auth.launch_token_path,
            "started_at": datetime.now().isoformat(),
            "version": hub_config.version,
        }, f, ensure_ascii=True, indent=2)

    logger.info("Hub 已启动: %s", hub_config.base_url)
    yield

    supervisor.stop_all()
    if os.path.exists(runtime_path):
        os.remove(runtime_path)
    logger.info("Hub 已关闭")


app = FastAPI(title="Hy127 Hub", lifespan=lifespan)


@app.middleware("http")
async def exact_origin_cors(request: Request, call_next):
    """Allow CORS only for the exact runtime Hub origin.

    Same-origin browser traffic does not need CORS, but an exact-origin response
    keeps preflight behavior deterministic and prevents other localhost ports
    from receiving credentialed access.
    """
    origin = request.headers.get("origin", "")
    expected_origin = f"http://127.0.0.1:{hub_config.port}"
    if request.method == "OPTIONS" and origin:
        if origin != expected_origin:
            return Response(status_code=403)
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,PATCH,OPTIONS",
                "Access-Control-Allow-Headers": request.headers.get(
                    "access-control-request-headers", "*"
                ),
                "Vary": "Origin",
            },
        )

    response = await call_next(request)
    if origin == expected_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    return response


# ── Identity (no auth required) ──

@app.get("/api/hub/identity")
async def hub_identity():
    return {"service": "hy127_hub", "version": hub_config.version}


# ── Bootstrap auth ──

@app.get("/bootstrap")
async def bootstrap(code: str):
    return auth.handle_bootstrap(code)


# ── Internal APIs (launch_token required) ──

@app.post("/internal/projects/register")
async def register_project(request: Request):
    auth.require_launch_token(request)
    body = await request.json()
    root_path = body.get("root_path")
    if not root_path:
        raise HTTPException(400, "缺少 root_path")

    try:
        project = registry.register(root_path)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    workspace_id = project["workspace_id"]

    supervisor.start_worker(workspace_id, root_path)
    return project


@app.post("/internal/bootstrap-code")
async def create_bootstrap_code(request: Request):
    auth.require_launch_token(request)
    body = await request.json()
    target = body.get("target", "/")
    code = auth.create_bootstrap_code(target)
    return {"code": code}


@app.post("/internal/ai/relay")
async def ai_relay(request: Request):
    """Internal AI relay: Worker calls this, Hub injects API key and proxies to provider.
    Authenticated by Worker token (matched against any active worker)."""
    worker_token = request.headers.get("X-Worker-Token", "")
    if not any(
        w.internal_token == worker_token
        for w in supervisor._workers.values()
    ):
        raise HTTPException(403, "Worker token 无效")

    body = await request.json()
    messages = body.get("messages", [])

    selected_model_id = body.get("model_id") or body.get("selected_model_id")
    runtime = body.get("runtime") or "api"

    if runtime not in ("api", "direct_api"):
        raise HTTPException(400, f"运行方式 {runtime} 已预留，CLI 桥接尚未启用")

    if selected_model_id:
        model = models_mgr.get_model(selected_model_id)
        if not model or not model.get("enabled"):
            raise HTTPException(400, "指定的 AI 模型不存在或未启用")
    else:
        model = models_mgr.get_default_model()

    if not model:
        raise HTTPException(400, "未配置 AI 模型")

    protocol = model.get("protocol") or "openai_chat"
    if protocol not in ("openai_chat", "openai_compatible"):
        raise HTTPException(400, f"模型协议 {protocol} 已保存，但当前对话暂未接入")

    api_key = models_mgr.get_api_key(model["id"])
    if not api_key:
        raise HTTPException(400, "API Key 未配置")

    ai_runtime = DirectHttpRuntime(
        api_base=model["api_base"],
        api_key=api_key,
        timeout=120,
    )

    async def _stream_sse():
        async for chunk in ai_runtime.chat(
            messages=messages,
            model=model["model_id"],
            stream=body.get("stream", True),
        ):
            if chunk.get("type") == "content":
                sse_data = json.dumps({"type": "content", "data": chunk["data"]})
                yield f"data: {sse_data}\n\n".encode("utf-8")
            elif chunk.get("type") == "error":
                sse_data = json.dumps({"type": "error", "data": chunk["data"]})
                yield f"data: {sse_data}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    from starlette.responses import StreamingResponse as _SR
    return _SR(_stream_sse(), media_type="text/event-stream")


# ── Hub APIs (session cookie required) ──

@app.get("/api/hub/projects")
async def list_projects(request: Request):
    auth.require_session(request)
    projects = registry.list_all()
    workers = {w["workspace_id"]: w for w in supervisor.list_workers()}
    for p in projects:
        w = workers.get(p["workspace_id"])
        p["worker_status"] = w["status"] if w else "stopped"
    return {"projects": projects}


@app.delete("/api/hub/projects/{workspace_id}")
async def remove_project(workspace_id: str, request: Request):
    auth.require_csrf(request)
    supervisor.stop_worker(workspace_id)
    removed = registry.remove(workspace_id)
    if not removed:
        raise HTTPException(404, "项目不存在")
    return {"status": "ok"}


@app.post("/api/hub/projects/{workspace_id}/start")
async def start_project_worker(workspace_id: str, request: Request):
    auth.require_csrf(request)
    project = registry.get(workspace_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    supervisor.start_worker(workspace_id, project["root_path"])
    return {"status": "ok"}


@app.post("/api/hub/projects/{workspace_id}/stop")
async def stop_project_worker(workspace_id: str, request: Request):
    auth.require_csrf(request)
    supervisor.stop_worker(workspace_id)
    return {"status": "ok"}


@app.post("/api/hub/projects/{workspace_id}/restart")
async def restart_project_worker(workspace_id: str, request: Request):
    auth.require_csrf(request)
    project = registry.get(workspace_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    supervisor.restart_worker(workspace_id, project["root_path"])
    return {"status": "ok"}


@app.get("/api/hub/status")
async def hub_status(request: Request):
    auth.require_session(request)
    return {
        "workers": supervisor.list_workers(),
        "projects_count": len(registry.list_all()),
    }


# ── AI model management ──

@app.get("/api/hub/models")
async def list_models(request: Request):
    auth.require_session(request)
    return {"models": models_mgr.list_models()}


@app.post("/api/hub/models")
async def add_or_update_model(request: Request):
    auth.require_csrf(request)
    body = await request.json()
    mid = body.get("id")
    optional = {
        k: body[k]
        for k in (
            "protocol", "runtime", "roles", "reasoning_profile",
            "enabled", "is_default", "orchestration",
        )
        if k in body
    }
    if mid:
        model = models_mgr.update_model(
            mid,
            name=body.get("name"),
            provider=body.get("provider"),
            api_base=body.get("api_base"),
            model_id=body.get("model_id"),
            api_key=body.get("api_key"),
            **optional,
        )
        if not model:
            raise HTTPException(404, "模型不存在")
        return model
    required = ["name", "provider", "api_base", "api_key", "model_id"]
    for field in required:
        if field not in body:
            raise HTTPException(400, f"缺少字段: {field}")
    return models_mgr.add_model(**{k: body[k] for k in required}, **optional)


@app.delete("/api/hub/models/{model_id}")
async def delete_model(model_id: str, request: Request):
    auth.require_csrf(request)
    if not models_mgr.remove_model(model_id):
        raise HTTPException(404, "模型不存在")
    return {"ok": True}


@app.post("/api/hub/models/{model_id}/test")
async def test_model(model_id: str, request: Request):
    auth.require_csrf(request)
    return await models_mgr.test_model(model_id)


# ── Sub-agent 绑定管理 ──

@app.get("/api/hub/subagent/status")
async def subagent_status(request: Request):
    auth.require_session(request)
    return subagent_mgr.get_status()


@app.get("/api/hub/subagent/candidates")
async def subagent_candidates(request: Request):
    auth.require_session(request)
    return {"candidates": subagent_mgr.list_candidates()}


@app.get("/api/hub/subagent/binding")
async def subagent_get_binding(request: Request):
    auth.require_session(request)
    return subagent_mgr.get_binding()


@app.post("/api/hub/subagent/binding")
async def subagent_save_binding(request: Request):
    auth.require_csrf(request)
    body = await request.json()
    agents = body.get("agents")
    if not isinstance(agents, dict):
        raise HTTPException(400, "缺少 agents 字段")

    errors = subagent_mgr.validate_agents(agents)
    if errors:
        raise HTTPException(400, {"errors": errors})

    result = subagent_mgr.save_and_render(agents)
    return {
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "errors": result.errors,
        "ok": result.ok,
    }


@app.get("/api/hub/subagent/agents")
async def subagent_rendered_agents(request: Request):
    auth.require_session(request)
    return {"agents": subagent_mgr.list_rendered_agents()}


@app.post("/api/hub/subagent/ccr/test")
async def subagent_ccr_test(request: Request):
    auth.require_csrf(request)
    return subagent_mgr.detect_ccr()


def _runtime_available(commands: list[str]) -> tuple[bool, str]:
    for cmd in commands:
        path = shutil.which(cmd)
        if path:
            return True, path
    return False, ""


@app.get("/api/hub/runtimes")
async def list_runtimes(request: Request):
    auth.require_session(request)
    presets = [
        {
            "id": "api",
            "name": "直接 API",
            "kind": "api",
            "implemented": True,
            "available": True,
            "description": "普通对话和文件问答，当前版本已启用",
        },
        {
            "id": "claude_cli",
            "name": "Claude Code",
            "kind": "cli",
            "commands": ["claude"],
            "implemented": False,
            "description": "预留：后续通过 Claude CLI 提供编程 Agent 对话",
        },
        {
            "id": "codex_cli",
            "name": "Codex CLI",
            "kind": "cli",
            "commands": ["codex"],
            "implemented": False,
            "description": "预留：后续通过 Codex CLI 提供编程 Agent 对话",
        },
        {
            "id": "qwen_cli",
            "name": "Qwen Code",
            "kind": "cli",
            "commands": ["qwen", "qwen-code"],
            "implemented": False,
            "description": "预留：后续接入 Qwen 编程运行时",
        },
        {
            "id": "gemini_cli",
            "name": "Gemini CLI",
            "kind": "cli",
            "commands": ["gemini"],
            "implemented": False,
            "description": "预留：后续通过 Gemini CLI 提供 Agent 对话",
        },
    ]
    for preset in presets:
        if preset.get("kind") == "cli":
            available, path = _runtime_available(preset["commands"])
            preset["available"] = available
            preset["path"] = path
    return {"runtimes": presets}


# ── Workspace API proxy to Worker ──

@app.api_route(
    "/api/workspaces/{workspace_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def workspace_api_proxy(workspace_id: str, path: str, request: Request):
    auth.require_session(request)
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        auth.require_csrf(request)
    return await proxy_http_to_worker(workspace_id, request, supervisor)


@app.websocket("/ws/workspaces/{workspace_id}/{path:path}")
async def workspace_ws_proxy(ws: WebSocket, workspace_id: str, path: str):
    await proxy_ws_to_worker(
        ws, workspace_id, path, supervisor,
        auth.verify_session,
        allowed_origin=auth._allowed_origin,
        session_cookie_names=auth.SESSION_COOKIE_NAMES,
    )


# ── Frontend SPA (catch-all) ──

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    from starlette.responses import FileResponse

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Serve static files directly if they exist
        static_file = os.path.join(static_dir, path)
        if path and os.path.isfile(static_file):
            return FileResponse(static_file)
        asset_prefixes = ("assets/", "vendor/")
        asset_exts = (
            ".css", ".js", ".mjs", ".map", ".wasm", ".json",
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2",
        )
        if path and (path.startswith(asset_prefixes) or path.endswith(asset_exts)):
            raise HTTPException(404, "static asset not found")
        index = os.path.join(static_dir, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(404, "前端文件未找到")


def main():
    import uvicorn

    env_port = os.environ.get("HY127WEB_HUB_PORT", "") or os.environ.get("CODE880WEB_HUB_PORT", "")
    env_port = env_port.strip()
    if env_port and env_port.isdigit():
        port = int(env_port)
    else:
        port = find_available_port()
    hub_config.port = port
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
