import argparse
import asyncio
import os
import re

from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response

from .services.ai_service import AIService
from .services.entrypoints import discover_entrypoints
from .services.file_service import FileService
from .services.git_service import GitService
from .services.preview_service import PreviewService
from .services.python_env_service import PythonEnvService
from .services.task_runner import TaskRunner
from .services.run_config_service import RunConfigService

RUN_ID_RE = re.compile(r"^[a-f0-9]{8}$")

INTERNAL_TOKEN: str = ""
PROJECT_ROOT: str = ""

app = FastAPI(title="Code880 Worker")

file_service: FileService | None = None
preview_service: PreviewService | None = None
task_runner: TaskRunner | None = None
ai_service: AIService | None = None
git_service: GitService | None = None
python_env_service: PythonEnvService | None = None
run_config_service: RunConfigService | None = None


def _read_hub_base_url() -> str:
    import json as _json

    candidates = []
    for env_name in ("HY127WEB_GLOBAL_DIR", "CODE880WEB_GLOBAL_DIR"):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append(value)

    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        candidates.append(os.path.join(localappdata, "Hy127Web"))
        candidates.append(os.path.join(localappdata, "Code880Web"))

    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if not state_home:
        state_home = os.path.join(os.path.expanduser("~"), ".local", "state")
    candidates.append(os.path.join(state_home, "hy127web"))

    for global_dir in candidates:
        runtime_path = os.path.join(global_dir, "hub_runtime.json")
        if os.path.isfile(runtime_path):
            with open(runtime_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            return data.get("base_url", "")
    return ""


def init_services(project_root: str):
    global file_service, preview_service, task_runner, ai_service, git_service, python_env_service, run_config_service, PROJECT_ROOT
    PROJECT_ROOT = project_root
    file_service = FileService(project_root)
    preview_service = PreviewService(project_root)
    task_runner = TaskRunner(project_root)
    ai_service = AIService(
        project_root,
        hub_base_url=_read_hub_base_url(),
        hub_worker_token=INTERNAL_TOKEN,
    )
    git_service = GitService(project_root)
    python_env_service = PythonEnvService(project_root)
    run_config_service = RunConfigService(project_root)


# ── Token verification middleware ──

@app.middleware("http")
async def verify_worker_token(request: Request, call_next):
    if request.headers.get("X-Worker-Token") != INTERNAL_TOKEN:
        return JSONResponse(status_code=403, content={"error": "forbidden"})
    return await call_next(request)


# ── Project info ──

@app.get("/api/info")
async def workspace_info():
    return {
        "project_root": PROJECT_ROOT,
        "name": os.path.basename(PROJECT_ROOT),
    }


# ── File tree ──

@app.get("/api/files/tree")
async def files_tree(path: str = "", depth: int = 3):
    return {"tree": file_service.get_tree(path, depth)}


@app.get("/api/files/content")
async def files_content(path: str):
    try:
        return file_service.read_file(path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/files/save")
async def files_save(request: Request):
    body = await request.json()
    path = body.get("path")
    content = body.get("content")
    base_sha256 = body.get("base_sha256")
    if not path or content is None:
        raise HTTPException(400, "缺少 path 或 content")
    try:
        return file_service.save_file(path, content, base_sha256)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/files/search")
async def files_search(q: str = "", max_results: int = 50):
    if not q:
        return {"results": []}
    return {"results": file_service.search_files(q, max_results)}


# ── File management ──

# PROTECTED_TOP_NAMES enforcement moved into FileService layer


@app.post("/api/files/create")
async def files_create(request: Request):
    body = await request.json()
    rel_path = body.get("path")
    if not rel_path:
        raise HTTPException(400, "缺少 path")
    try:
        return file_service.create_file(rel_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@app.post("/api/files/mkdir")
async def files_mkdir(request: Request):
    body = await request.json()
    rel_path = body.get("path")
    if not rel_path:
        raise HTTPException(400, "缺少 path")
    try:
        return file_service.create_dir(rel_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@app.post("/api/files/rename")
async def files_rename(request: Request):
    body = await request.json()
    rel_path = body.get("path")
    new_name = body.get("new_name")
    if not rel_path or not new_name:
        raise HTTPException(400, "缺少 path 或 new_name")
    try:
        return file_service.rename(rel_path, new_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))


@app.delete("/api/files/delete")
async def files_delete(request: Request):
    body = await request.json()
    rel_path = body.get("path")
    soft = body.get("soft", True)
    if not rel_path:
        raise HTTPException(400, "缺少 path")
    try:
        return file_service.delete_file(rel_path, soft=soft)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/files/copy")
async def files_copy(request: Request):
    body = await request.json()
    src = body.get("src")
    dst = body.get("dst")
    if not src or not dst:
        raise HTTPException(400, "缺少 src 或 dst")
    try:
        return file_service.copy_path(src, dst)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))


# ── Python environment ──

@app.get("/api/python/interpreters")
async def python_interpreters():
    return python_env_service.list_interpreters()


@app.post("/api/python/interpreters/select")
async def python_select_interpreter(request: Request):
    body = await request.json()
    path = body.get("path")
    if not path:
        raise HTTPException(400, "缺少 path")
    try:
        return python_env_service.set_project_interpreter(path)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/python/env")
async def python_env():
    return python_env_service.inspect_environment()


# ── Git (read-only) ──

@app.get("/api/git/available")
async def git_available():
    return git_service.available()


@app.get("/api/git/status")
async def git_status():
    try:
        return git_service.status()
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/git/diff")
async def git_diff(path: str = ""):
    try:
        return git_service.diff(path)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/git/branch")
async def git_branch():
    try:
        return git_service.branch()
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/git/log")
async def git_log(max_count: int = 20):
    try:
        return git_service.log(max_count)
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/git/commit-message")
async def git_commit_message():
    try:
        return git_service.generate_commit_message()
    except RuntimeError as e:
        raise HTTPException(400, str(e))


# ── Preview ──

@app.get("/api/preview/{path:path}")
async def preview_file(path: str):
    try:
        return preview_service.preview(path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/preview-stream")
async def preview_stream(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            data = preview_service.get_pdf_bytes(path)
            return Response(content=data, media_type="application/pdf")
        except ValueError as e:
            raise HTTPException(400, str(e))
    # Images
    from .services.file_service import IMAGE_EXTENSIONS
    if ext in IMAGE_EXTENSIONS:
        from .services.security import validate_path
        if not validate_path(PROJECT_ROOT, path):
            raise HTTPException(400, "路径不合法")
        abs_path = os.path.join(PROJECT_ROOT, path)
        if not os.path.isfile(abs_path):
            raise HTTPException(404, "文件不存在")
        media_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
            ".bmp": "image/bmp", ".ico": "image/x-icon",
        }
        with open(abs_path, "rb") as f:
            data = f.read()
        return Response(content=data, media_type=media_types.get(ext, "application/octet-stream"))
    raise HTTPException(400, "不支持的文件类型")


# ── Run Python files ──

@app.get("/api/entrypoints")
async def get_entrypoints():
    return {"entrypoints": discover_entrypoints(PROJECT_ROOT)}


@app.post("/api/run")
async def start_run(request: Request):
    body = await request.json()
    program = body.get("program")
    args = body.get("args", [])
    if not program:
        raise HTTPException(400, "缺少 program")
    try:
        run_id = await task_runner.start_run(program, args)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    asyncio.create_task(task_runner.read_output_and_broadcast(run_id))
    return {"run_id": run_id, "status": "running"}


@app.get("/api/run/{run_id}")
async def get_run_status(run_id: str):
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    task = task_runner.running_tasks.get(run_id)
    if task:
        return {
            "status": "running",
            "file": task["file"],
            "pid": task["pid"],
            "started_at": task["started_at"],
        }
    completed = task_runner.get_completed(run_id)
    if completed:
        return {
            "status": "finished",
            "file": completed["file"],
            "exit_code": completed["exit_code"],
            "elapsed": completed["elapsed"],
        }
    return {"status": "not_found"}


@app.post("/api/run/{run_id}/stdin")
async def send_stdin(run_id: str, request: Request):
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    body = await request.json()
    try:
        await task_runner.send_stdin(run_id, body["input"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"status": "ok"}


@app.post("/api/run/{run_id}/stop")
async def stop_run(run_id: str):
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    await task_runner.stop_run(run_id)
    return {"status": "stopped"}


@app.get("/api/run/history")
async def run_history():
    return {"runs": task_runner.get_run_history()}


@app.post("/api/run/config")
async def run_config_save(request: Request):
    body = await request.json()
    try:
        return run_config_service.save(body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/run/config")
async def run_config_load():
    return run_config_service.load()


@app.get("/api/run/{run_id}/log")
async def get_run_log(run_id: str):
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "run_id 格式不合法")
    log_path = os.path.join(PROJECT_ROOT, ".web-workbench", "runs", f"{run_id}.log")
    if not os.path.exists(log_path):
        raise HTTPException(404, "日志不存在")
    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"run_id": run_id, "log": content}


# ── Run WebSocket ──

@app.websocket("/ws/run/{run_id}")
async def ws_run_output(ws: WebSocket, run_id: str):
    if not RUN_ID_RE.match(run_id):
        await ws.close(code=4002)
        return

    token = ws.headers.get("X-Worker-Token")
    if token != INTERNAL_TOKEN:
        await ws.close(code=4003)
        return

    await ws.accept()

    completed = task_runner.get_completed(run_id)
    if completed:
        log_path = completed.get("log_path")
        if log_path and os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            if log_content:
                await ws.send_json({
                    "type": "run_output",
                    "run_id": run_id,
                    "data": log_content,
                })
        await ws.send_json({
            "type": "run_finished",
            "run_id": run_id,
            "exit_code": completed["exit_code"],
            "elapsed": completed["elapsed"],
        })
        await ws.close()
        return

    task_runner.register_ws_client(run_id, ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "stdin":
                await task_runner.send_stdin(run_id, data["input"])
    except Exception:
        pass
    finally:
        task_runner.remove_ws_client(run_id, ws)


# ── AI chat ──

@app.post("/api/ai/chat")
async def ai_chat(request: Request):
    body = await request.json()
    message = body.get("message", "")
    if not message:
        raise HTTPException(400, "缺少 message")
    return StreamingResponse(
        ai_service.chat_stream(
            message,
            model_id=body.get("model_id", ""),
            runtime=body.get("runtime", "api"),
            thinking_profile=body.get("thinking_profile", "max"),
        ),
        media_type="text/event-stream",
    )


@app.get("/api/ai/context")
async def ai_context_get():
    return {"files": ai_service.get_context_files()}


@app.post("/api/ai/context")
async def ai_context_set(request: Request):
    body = await request.json()
    files = body.get("files", [])
    ai_service.set_context_files(files)
    return {"status": "ok", "files": ai_service.get_context_files()}


@app.get("/api/ai/history")
async def ai_history():
    return {"history": ai_service.get_chat_history()}


@app.post("/api/ai/history/clear")
async def ai_clear_history():
    ai_service.clear_chat_history()
    return {"status": "ok"}


# ── Main entry ──

def main():
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    # Token file path passed via env var (not cmdline) to avoid WMI/process-list exposure
    token_file = os.environ.get("CODE880_WORKER_TOKEN_FILE", "")
    if not token_file or not os.path.isfile(token_file):
        raise RuntimeError("CODE880_WORKER_TOKEN_FILE 环境变量未设置或文件不存在")

    global INTERNAL_TOKEN
    with open(token_file, "r") as f:
        INTERNAL_TOKEN = f.read().strip()
    os.remove(token_file)

    init_services(args.project_root)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
