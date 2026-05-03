import asyncio
import logging

import httpx
from fastapi import Request, WebSocket, HTTPException
from starlette.responses import StreamingResponse

from .supervisor import WorkerSupervisor

logger = logging.getLogger("hub.proxy")

HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})


def rewrite_http_path(original_path: str, workspace_id: str) -> str:
    prefix = f"/api/workspaces/{workspace_id}"
    if original_path.startswith(prefix):
        remainder = original_path[len(prefix):]
        return f"/api{remainder}" if remainder else "/api"
    return original_path


def rewrite_ws_path(original_path: str, workspace_id: str) -> str:
    prefix = f"/ws/workspaces/{workspace_id}"
    if original_path.startswith(prefix):
        remainder = original_path[len(prefix):]
        return f"/ws{remainder}" if remainder else "/ws"
    return original_path


async def proxy_http_to_worker(
    workspace_id: str,
    request: Request,
    supervisor: WorkerSupervisor,
):
    worker = supervisor.get_worker(workspace_id)
    if not worker or worker.status != "running":
        raise HTTPException(502, "Worker 未运行")

    headers = dict(request.headers)
    headers["X-Worker-Token"] = worker.internal_token

    worker_path = rewrite_http_path(request.url.path, workspace_id)
    worker_url = f"http://127.0.0.1:{worker.port}{worker_path}"
    if request.url.query:
        worker_url += f"?{request.url.query}"

    client = httpx.AsyncClient()
    try:
        req = client.build_request(
            method=request.method,
            url=worker_url,
            headers=headers,
            content=await request.body(),
        )
        worker_resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        logger.error("代理请求失败: %s", e)
        raise HTTPException(502, "Worker 连接失败")

    resp_headers = {
        k: v for k, v in worker_resp.headers.items()
        if k.lower() not in HOP_BY_HOP
    }

    async def stream_body():
        try:
            async for chunk in worker_resp.aiter_bytes():
                yield chunk
        finally:
            await worker_resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_body(),
        status_code=worker_resp.status_code,
        headers=resp_headers,
    )


async def proxy_ws_to_worker(
    ws_client: WebSocket,
    workspace_id: str,
    path: str,
    supervisor: WorkerSupervisor,
    verify_session_fn,
    allowed_origin: str = "",
):
    session_id = ws_client.cookies.get("code880_session")
    if not session_id or not verify_session_fn(session_id):
        await ws_client.close(code=4001)
        return

    origin = ws_client.headers.get("origin")
    if origin and origin != allowed_origin:
        await ws_client.close(code=4003)
        return

    worker = supervisor.get_worker(workspace_id)
    if not worker or worker.status != "running":
        await ws_client.close(code=4004)
        return

    await ws_client.accept()

    worker_ws_url = f"ws://127.0.0.1:{worker.port}/ws/{path}"
    extra_headers = {"X-Worker-Token": worker.internal_token}

    try:
        import websockets

        async with websockets.connect(
            worker_ws_url, additional_headers=extra_headers
        ) as ws_worker:

            async def client_to_worker():
                try:
                    async for msg in ws_client.iter_text():
                        await ws_worker.send(msg)
                except Exception:
                    pass

            async def worker_to_client():
                try:
                    async for msg in ws_worker:
                        await ws_client.send_text(msg)
                except Exception:
                    pass

            task_c2w = asyncio.create_task(client_to_worker())
            task_w2c = asyncio.create_task(worker_to_client())

            done, pending = await asyncio.wait(
                {task_c2w, task_w2c},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            for t in pending:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
    except Exception:
        pass
    finally:
        try:
            await ws_client.close()
        except Exception:
            pass
