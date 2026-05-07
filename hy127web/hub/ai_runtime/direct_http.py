import json
from collections.abc import AsyncGenerator

import httpx

from .base import AIRuntime
from .errors import AuthenticationError, ProviderError, RateLimitError, TimeoutError


class DirectHttpRuntime(AIRuntime):
    """OpenAI-compatible /chat/completions direct HTTP runtime."""

    def __init__(self, api_base: str, api_key: str, timeout: float = 120):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   model: str = "", stream: bool = True) -> AsyncGenerator[dict, None]:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code == 401:
                        yield {"type": "error", "data": "API Key 认证失败"}
                        return
                    if resp.status_code == 429:
                        yield {"type": "error", "data": "请求频率过高，请稍后重试"}
                        return
                    if resp.status_code >= 400:
                        yield {"type": "error", "data": f"服务错误 ({resp.status_code})"}
                        return

                    if stream:
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":
                                    return
                                try:
                                    chunk = json.loads(data_str)
                                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield {"type": "content", "data": content}
                                except (json.JSONDecodeError, KeyError, IndexError):
                                    pass
                    else:
                        data = resp.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            yield {"type": "content", "data": content}
        except httpx.TimeoutException:
            yield {"type": "error", "data": "AI 请求超时"}
        except httpx.ConnectError:
            yield {"type": "error", "data": "无法连接 AI 服务"}
        except Exception as e:
            yield {"type": "error", "data": str(e)}
