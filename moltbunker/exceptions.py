"""Moltbunker SDK Exceptions"""

from typing import Any, Dict, Optional


class MoltbunkerError(Exception):
    """Base exception for all Moltbunker errors"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthenticationError(MoltbunkerError):
    """Raised when authentication fails (invalid API key or wallet signature)"""

    pass


class NotFoundError(MoltbunkerError):
    """Raised when a resource is not found"""

    pass


class RateLimitError(MoltbunkerError):
    """Raised when rate limit is exceeded"""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        status_code: Optional[int] = 429,
        response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, status_code, response)
        self.retry_after = retry_after


class InsufficientFundsError(MoltbunkerError):
    """Raised when wallet has insufficient BUNKER tokens"""

    def __init__(
        self,
        message: str = "Insufficient BUNKER tokens",
        required: Optional[float] = None,
        available: Optional[float] = None,
        status_code: Optional[int] = 402,
        response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, status_code, response)
        self.required = required
        self.available = available

    def __str__(self) -> str:
        msg = self.message
        if self.required is not None and self.available is not None:
            msg += f" (required: {self.required} BUNKER, available: {self.available} BUNKER)"
        return msg


class DeploymentError(MoltbunkerError):
    """Raised when deployment fails"""

    def __init__(
        self,
        message: str,
        deployment_id: Optional[str] = None,
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, status_code, response)
        self.deployment_id = deployment_id


class CloneError(MoltbunkerError):
    """Raised when cloning fails"""

    def __init__(
        self,
        message: str,
        clone_id: Optional[str] = None,
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, status_code, response)
        self.clone_id = clone_id


class SnapshotError(MoltbunkerError):
    """Raised when snapshot operations fail"""

    def __init__(
        self,
        message: str,
        snapshot_id: Optional[str] = None,
        status_code: Optional[int] = None,
        response: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, status_code, response)
        self.snapshot_id = snapshot_id


class ValidationError(MoltbunkerError):
    """Raised when input validation fails"""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
    ):
        super().__init__(message)
        self.field = field
        self.value = value


class ConnectionError(MoltbunkerError):
    """Raised when connection to the API fails"""

    pass


class TimeoutError(MoltbunkerError):
    """Raised when an operation times out"""

    pass


class RuntimeNotFoundError(NotFoundError):
    """Raised when runtime is not found"""

    pass


class BotNotFoundError(NotFoundError):
    """Raised when bot is not found"""

    pass


class ContainerNotFoundError(NotFoundError):
    """Raised when container is not found"""

    pass
