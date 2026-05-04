from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class AIRuntime(ABC):
    """Abstract base for pluggable AI runtimes."""

    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   model: str = "", stream: bool = True) -> AsyncGenerator[dict, None]:
        """Stream chat completions. Yields {"type": "content", "data": str} or {"type": "error", "data": str}."""
        yield {"type": "error", "data": "not implemented"}
