from .base import AIRuntime

__all__ = ["AIRuntime", "CliRuntime", "DirectHttpRuntime"]


def __getattr__(name):
    if name == "CliRuntime":
        from .cli_runtime import CliRuntime
        return CliRuntime
    if name == "DirectHttpRuntime":
        from .direct_http import DirectHttpRuntime
        return DirectHttpRuntime
    raise AttributeError(name)
