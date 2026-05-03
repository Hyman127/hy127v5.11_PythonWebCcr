import json
import os

import httpx


class AIService:
    """Worker-side AI service.

    Worker never holds API keys. All AI requests are relayed through Hub's
    internal /internal/ai/relay endpoint, where Hub injects the decrypted key.
    """

    def __init__(self, project_root: str, hub_base_url: str = "", hub_worker_token: str = ""):
        self.project_root = project_root
        self.hub_base_url = hub_base_url
        self.hub_worker_token = hub_worker_token
        self._context_files: list[str] = []
        self._chat_history: list[dict] = []

    def set_context_files(self, files: list[str]):
        self._context_files = files

    def get_context_files(self) -> list[str]:
        return self._context_files

    def _build_context(self) -> str:
        parts = []
        for rel_path in self._context_files:
            abs_path = os.path.join(self.project_root, rel_path)
            if not os.path.isfile(abs_path):
                continue
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(50000)
                parts.append(f"=== {rel_path} ===\n{content}")
            except Exception:
                continue
        return "\n\n".join(parts)

    @staticmethod
    def _thinking_instruction(profile: str) -> str:
        if profile == "quick":
            return "请用简洁方式回答，优先给出可执行结论。"
        if profile == "standard":
            return "请在准确性和效率之间保持平衡，必要时给出关键依据。"
        if profile == "deep":
            return "请进行较深入分析，先判断问题结构，再给出步骤化建议。"
        return (
            "请按最佳质量模式回答：先充分分析问题和上下文，"
            "再给出清晰结论、风险点和可执行步骤。"
        )

    async def chat_stream(
        self,
        user_message: str,
        model_id: str = "",
        runtime: str = "api",
        thinking_profile: str = "max",
    ):
        if not self.hub_base_url:
            yield json.dumps({"type": "error", "data": "Hub 地址未配置"}) + "\n"
            return

        context = self._build_context()
        system_prompt = "你是 Code880 编程助手。"
        system_prompt += "\n" + self._thinking_instruction(thinking_profile)
        if context:
            system_prompt += f"\n\n以下是用户选定的项目文件内容，请基于这些文件回答：\n\n{context}"

        self._chat_history.append({"role": "user", "content": user_message})

        messages = [{"role": "system", "content": system_prompt}] + self._chat_history[-20:]

        relay_url = f"{self.hub_base_url}/internal/ai/relay"
        headers = {
            "X-Worker-Token": self.hub_worker_token,
            "Content-Type": "application/json",
        }
        body = {
            "messages": messages,
            "stream": True,
            "model_id": model_id,
            "runtime": runtime,
            "thinking_profile": thinking_profile,
        }

        full_response = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", relay_url, json=body, headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        text = ""
                        async for chunk in resp.aiter_bytes():
                            text += chunk.decode("utf-8", errors="replace")
                        yield json.dumps({"type": "error", "data": f"Hub AI relay 返回 {resp.status_code}: {text[:200]}"}) + "\n"
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                yield json.dumps({"type": "content", "data": content}) + "\n"
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as e:
            yield json.dumps({"type": "error", "data": str(e)}) + "\n"
            return

        self._chat_history.append({"role": "assistant", "content": full_response})
        yield json.dumps({"type": "done"}) + "\n"

    def get_chat_history(self) -> list[dict]:
        return self._chat_history

    def clear_chat_history(self):
        self._chat_history.clear()
