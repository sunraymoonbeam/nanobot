"""Lark SDK client factory.

Creates and caches a lark_oapi.Client from Feishu channel credentials.
Shared by all Lark tools so they reuse the same authenticated client.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LarkClientFactory:
    """Lazy-initialised Lark SDK client."""

    def __init__(self, app_id: str, app_secret: str, domain: str = "feishu"):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._client = None

    @property
    def client(self):
        """Return the cached lark.Client, creating it on first access."""
        if self._client is None:
            import lark_oapi as lark

            builder = (
                lark.Client.builder()
                .app_id(self._app_id)
                .app_secret(self._app_secret)
                .log_level(lark.LogLevel.INFO)
            )
            if self._domain == "lark":
                builder = builder.domain(lark.LARK_DOMAIN)
            self._client = builder.build()
            logger.info("Lark client created (domain=%s)", self._domain)
        return self._client
