class AIRuntimeError(Exception):
    """Base exception for AI runtime errors."""
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


class AuthenticationError(AIRuntimeError):
    """API key or authentication failure."""
    pass


class RateLimitError(AIRuntimeError):
    """Rate limit exceeded."""
    pass


class ProviderError(AIRuntimeError):
    """Provider-side error (4xx/5xx)."""
    pass


class TimeoutError(AIRuntimeError):
    """Request timeout."""
    pass
