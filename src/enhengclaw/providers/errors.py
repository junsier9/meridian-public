from __future__ import annotations


class ShadowProviderError(RuntimeError):
    pass


class RetryableTransportError(ShadowProviderError):
    pass


class FatalTransportError(ShadowProviderError):
    pass

