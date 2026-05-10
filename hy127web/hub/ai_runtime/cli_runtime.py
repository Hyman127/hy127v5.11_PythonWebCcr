import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

from .base import AIRuntime


OPENAI_COMPATIBLE_PROTOCOLS = {"openai_chat", "openai_compatible"}


class CliRuntime(AIRuntime):
    """Run a coding CLI in the selected project directory.

    The Hub owns API-key decryption. This runtime receives the selected model
    credentials and injects them into the child process environment.
    """

    RUNTIMES = {
        "claude_cli": {
            "name": "Claude Code",
            "commands": ["claude"],
        },
        "codex_cli": {
            "name": "Codex CLI",
            "commands": ["codex"],
        },
    }

    PROVIDER_KEY_ALIASES = {
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "qwen": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
        "moonshot": ["MOONSHOT_API_KEY"],
        "doubao": ["ARK_API_KEY"],
        "ark_coding_plan": ["ARK_CODING_PLAN_API_KEY"],
        "glm": ["ZHIPU_API_KEY"],
        "hunyuan": ["HUNYUAN_API_KEY"],
        "mimo": ["XIAOMI_API_KEY"],
        "minimax": ["MINIMAX_API_KEY"],
        "stepfun": ["STEPFUN_API_KEY"],
        "ernie": ["QIANFAN_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "openai_codex": ["OPENAI_API_KEY"],
    }

    PROVIDER_BASE_ALIASES = {
        "anthropic": ["ANTHROPIC_BASE_URL"],
        "gemini": ["GEMINI_BASE_URL", "GOOGLE_GEMINI_BASE_URL"],
        "qwen": ["DASHSCOPE_BASE_URL"],
        "deepseek": ["DEEPSEEK_BASE_URL"],
        "moonshot": ["MOONSHOT_BASE_URL"],
        "doubao": ["ARK_BASE_URL"],
        "ark_coding_plan": ["ARK_CODING_PLAN_BASE_URL"],
        "glm": ["ZHIPU_BASE_URL"],
        "hunyuan": ["HUNYUAN_BASE_URL"],
        "mimo": ["XIAOMI_BASE_URL"],
        "minimax": ["MINIMAX_BASE_URL"],
        "stepfun": ["STEPFUN_BASE_URL"],
        "ernie": ["QIANFAN_BASE_URL"],
        "openai": ["OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_BASE_URL"],
        "openai_codex": ["OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_BASE_URL"],
    }

    COMMON_OPENAI_BASE_ALIASES = [
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "OPENAI_API_BASE_URL",
    ]

    def __init__(
        self,
        *,
        runtime_id: str,
        cwd: str,
        provider: str = "",
        protocol: str = "openai_chat",
        model: str = "",
        api_key: str = "",
        api_base: str = "",
        env_key: str = "",
        timeout: float = 600,
    ):
        if runtime_id not in self.RUNTIMES:
            raise ValueError(f"未知 CLI 运行方式: {runtime_id}")
        self.runtime_id = runtime_id
        self.cwd = cwd
        self.provider = provider or ""
        self.protocol = protocol or "openai_chat"
        self.model = model or ""
        self.api_key = api_key or ""
        self.api_base = (api_base or "").rstrip("/")
        self.env_key = env_key or ""
        self.timeout = timeout

    @classmethod
    def is_supported_runtime(cls, runtime_id: str) -> bool:
        return runtime_id in cls.RUNTIMES

    @classmethod
    def command_available(cls, runtime_id: str) -> tuple[bool, str]:
        preset = cls.RUNTIMES.get(runtime_id)
        if not preset:
            return False, ""
        for command in preset["commands"]:
            path = shutil.which(command)
            if path:
                return True, path
        return False, ""

    @property
    def display_name(self) -> str:
        return self.RUNTIMES[self.runtime_id]["name"]

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "",
        stream: bool = True,
    ) -> AsyncGenerator[dict, None]:
        if not os.path.isdir(self.cwd):
            yield {"type": "error", "data": f"项目目录不存在: {self.cwd}"}
            return

        available, path = self.command_available(self.runtime_id)
        if not available:
            commands = "/".join(self.RUNTIMES[self.runtime_id]["commands"])
            yield {"type": "error", "data": f"未找到 {commands} 命令，请先安装并完成 CLI 登录或配置"}
            return

        prompt = self._messages_to_prompt(messages)
        try:
            output = await self._run_cli(path, prompt, model or self.model)
        except Exception as exc:
            yield {"type": "error", "data": str(exc)}
            return

        if output:
            yield {"type": "content", "data": output}
        else:
            yield {"type": "error", "data": f"{self.display_name} 返回空结果"}

    def _messages_to_prompt(self, messages: list[dict]) -> str:
        parts = [
            f"你正在项目目录执行任务: {self.cwd}",
            "请基于用户请求完成任务。若需要修改文件，请保持改动聚焦，并在最终输出中列出修改内容和验证结果。",
        ]
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = self._content_to_text(message.get("content", ""))
            if content:
                parts.append(f"{role}:\n{content}")
        return "\n\n".join(parts)

    @staticmethod
    def _content_to_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and item.get("text"):
                        chunks.append(str(item["text"]))
                    elif item.get("content"):
                        chunks.append(str(item["content"]))
                elif item:
                    chunks.append(str(item))
            return "\n".join(chunks)
        return str(content) if content else ""

    def _build_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        env = dict(base_env or os.environ)
        if self.api_key:
            key_names = set()
            if self.env_key:
                key_names.add(self.env_key)
            key_names.update(self.PROVIDER_KEY_ALIASES.get(self.provider, []))
            if self.protocol in OPENAI_COMPATIBLE_PROTOCOLS:
                key_names.add("OPENAI_API_KEY")
            if self.runtime_id == "claude_cli" or self.protocol == "anthropic_messages":
                key_names.add("ANTHROPIC_API_KEY")
            for key_name in key_names:
                if key_name:
                    env[key_name] = self.api_key

        if self.api_base.startswith(("http://", "https://")):
            base_names = set(self.PROVIDER_BASE_ALIASES.get(self.provider, []))
            if self.protocol in OPENAI_COMPATIBLE_PROTOCOLS:
                base_names.update(self.COMMON_OPENAI_BASE_ALIASES)
            if self.runtime_id == "claude_cli" or self.protocol == "anthropic_messages":
                base_names.add("ANTHROPIC_BASE_URL")
            for base_name in base_names:
                env[base_name] = self.api_base

        if self.model:
            env["HY127WEB_AI_MODEL"] = self.model
        if self.provider:
            env["HY127WEB_AI_PROVIDER"] = self.provider
        if self.api_base:
            env["HY127WEB_AI_BASE_URL"] = self.api_base
        return env

    async def _run_cli(self, executable: str, prompt: str, model: str) -> str:
        if self.runtime_id == "codex_cli":
            return await self._run_codex(executable, prompt, model)
        return await self._run_prompt_cli(executable, prompt, model)

    def _prompt_variants(self, prompt: str, model: str) -> list[tuple[list[str], str | None]]:
        variants: list[tuple[list[str], str | None]] = []
        if self.runtime_id == "claude_cli":
            if model:
                variants.extend([
                    (["--model", model, "-p", "--output-format", "text"], prompt),
                    (["--model", model, "-p"], prompt),
                ])
            variants.extend([
                (["-p", "--output-format", "text"], prompt),
                (["-p"], prompt),
            ])
            return variants

        return [([], prompt)]

    async def _run_prompt_cli(self, executable: str, prompt: str, model: str) -> str:
        last_error = ""
        for args, stdin_text in self._prompt_variants(prompt, model):
            result = await self._communicate(
                [executable, *args],
                stdin_text=stdin_text,
            )
            output = result["stdout"].strip()
            stderr = result["stderr"].strip()
            if result["returncode"] == 0 and output:
                return output
            last_error = stderr or output or f"{self.display_name} 调用失败"
        raise RuntimeError(self._format_cli_error(last_error))

    async def _run_codex(self, executable: str, prompt: str, model: str) -> str:
        output_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False,
            ) as tmp:
                output_path = tmp.name

            base_args = ["exec"]
            if model:
                base_args.extend(["-m", model])
            base_args.extend([
                "--skip-git-repo-check",
                "--sandbox", "workspace-write",
                "--color", "never",
                "-o", output_path,
                "-",
            ])
            fallback_args = [arg for arg in base_args if arg not in {"--sandbox", "workspace-write"}]

            last_error = ""
            for args in (base_args, fallback_args):
                result = await self._communicate([executable, *args], stdin_text=prompt)
                file_text = ""
                if output_path and os.path.exists(output_path):
                    file_text = Path(output_path).read_text(encoding="utf-8", errors="replace").strip()
                output = file_text or result["stdout"].strip()
                stderr = result["stderr"].strip()
                if result["returncode"] == 0 and output:
                    return output
                last_error = stderr or result["stdout"].strip() or "Codex CLI 调用失败"
            raise RuntimeError(self._format_cli_error(last_error))
        finally:
            if output_path:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

    async def _communicate(self, cmd: list[str], stdin_text: str | None = None) -> dict:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.cwd,
            env=self._build_env(),
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin_text.encode("utf-8") if stdin_text is not None else None),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"{self.display_name} 调用超时({int(self.timeout)}秒)，请减少输入规模")
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def _format_cli_error(self, text: str) -> str:
        clean = " ".join((text or "").split())
        if not clean:
            clean = f"{self.display_name} 调用失败"
        return f"{self.display_name}: {clean[:600]}"
