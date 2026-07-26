"""Typed provider failures for routing and user-facing error handling."""


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class ProviderTimeout(ProviderError):
    pass


class ProviderConnectionError(ProviderError):
    pass


class ProviderConfigError(ProviderError, ValueError):
    """Invalid provider configuration, compatible with legacy ValueError handlers."""

    pass
