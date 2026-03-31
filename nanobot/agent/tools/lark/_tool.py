"""Generic LarkTool adapter.

Bridges openclaw-python's tool registration pattern to nanobot's Tool base class.

openclaw-python registers tools as:
    api.register_tool(name=..., description=..., schema=..., handler=async_fn)
    where handler signature is: async def handler(params: dict, client) -> dict

nanobot expects Tool subclasses with:
    name, description, parameters properties + async execute(**kwargs) -> str

This adapter wraps any openclaw-style handler as a nanobot Tool.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable

from nanobot.agent.tools.base import Tool
from .client import LarkClientFactory


class LarkTool(Tool):
    """Wrap an openclaw-python Feishu tool handler as a nanobot Tool."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_schema: dict[str, Any],
        handler: Callable[[dict[str, Any], Any], Awaitable[dict[str, Any]]],
        client_factory: LarkClientFactory,
    ):
        self._name = tool_name
        self._description = tool_description
        self._schema = tool_schema
        self._handler = handler
        self._factory = client_factory

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs: Any) -> str:
        """Call the openclaw handler and return the JSON text result."""
        result = await self._handler(kwargs, self._factory.client)
        # openclaw handlers return {"content": [{"type": "text", "text": "..."}], "details": ...}
        content = result.get("content", [])
        if content and isinstance(content[0], dict):
            return content[0].get("text", str(result))
        return str(result)
