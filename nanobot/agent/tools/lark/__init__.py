"""Feishu/Lark tools plugin for nanobot.

Registers all Lark tools (doc, wiki, drive, chat, bitable, task, perm, urgent,
reactions, calendar) as first-class nanobot agent tools.

Ported from openclaw-python/extensions/feishu/ — action code copied verbatim,
only the registration layer is adapted to nanobot's Tool base class via LarkTool.
"""
from __future__ import annotations

import logging
from typing import Any

from nanobot.agent.tools.registry import ToolRegistry

from ._tool import LarkTool
from .client import LarkClientFactory

logger = logging.getLogger(__name__)


def register_lark_tools(
    registry: ToolRegistry,
    client_factory: LarkClientFactory,
    enabled_tools: dict[str, bool] | None = None,
) -> None:
    """Register all Lark tools with the agent's tool registry.

    Args:
        registry: The nanobot ToolRegistry to register tools into.
        client_factory: Factory providing a shared lark.Client instance.
        enabled_tools: Optional dict controlling which tool groups are enabled.
            Keys: doc, wiki, drive, chat, bitable, task, perm, urgent, reactions, calendar.
            Defaults to all enabled except perm (sensitive).
    """
    defaults = {
        "doc": True, "wiki": True, "drive": True, "chat": True,
        "bitable": True, "task": True, "perm": False,
        "urgent": True, "reactions": True, "calendar": True,
    }
    enabled = {**defaults, **(enabled_tools or {})}
    registered = []

    # ── Single-dispatch tools (one Tool wrapping a dispatcher function) ──

    if enabled.get("doc"):
        try:
            from .doc_handler import run_feishu_doc, run_feishu_app_scopes
            from .doc_schemas import (
                DOC_TOOL_NAME, DOC_TOOL_DESCRIPTION, DOC_TOOL_SCHEMA,
                SCOPES_TOOL_NAME, SCOPES_TOOL_DESCRIPTION, SCOPES_TOOL_SCHEMA,
            )
            registry.register(LarkTool(DOC_TOOL_NAME, DOC_TOOL_DESCRIPTION, DOC_TOOL_SCHEMA, run_feishu_doc, client_factory))
            registry.register(LarkTool(SCOPES_TOOL_NAME, SCOPES_TOOL_DESCRIPTION, SCOPES_TOOL_SCHEMA, run_feishu_app_scopes, client_factory))
            registered.extend([DOC_TOOL_NAME, SCOPES_TOOL_NAME])
        except Exception as e:
            logger.warning("Failed to register doc tools: %s", e)

    if enabled.get("wiki"):
        try:
            from .wiki_handler import TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, run_feishu_wiki
            registry.register(LarkTool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, run_feishu_wiki, client_factory))
            registered.append(TOOL_NAME)
        except Exception as e:
            logger.warning("Failed to register wiki tools: %s", e)

    if enabled.get("drive"):
        try:
            from .drive_handler import TOOL_NAME as DRIVE_NAME, TOOL_DESCRIPTION as DRIVE_DESC, TOOL_SCHEMA as DRIVE_SCHEMA, run_feishu_drive
            registry.register(LarkTool(DRIVE_NAME, DRIVE_DESC, DRIVE_SCHEMA, run_feishu_drive, client_factory))
            registered.append(DRIVE_NAME)
        except Exception as e:
            logger.warning("Failed to register drive tools: %s", e)

    if enabled.get("chat"):
        try:
            from .chat_handler import TOOL_NAME as CHAT_NAME, TOOL_DESCRIPTION as CHAT_DESC, TOOL_SCHEMA as CHAT_SCHEMA, run_feishu_chat
            registry.register(LarkTool(CHAT_NAME, CHAT_DESC, CHAT_SCHEMA, run_feishu_chat, client_factory))
            registered.append(CHAT_NAME)
        except Exception as e:
            logger.warning("Failed to register chat tools: %s", e)

    if enabled.get("perm"):
        try:
            from .perm_handler import TOOL_NAME as PERM_NAME, TOOL_DESCRIPTION as PERM_DESC, TOOL_SCHEMA as PERM_SCHEMA, run_feishu_perm
            registry.register(LarkTool(PERM_NAME, PERM_DESC, PERM_SCHEMA, run_feishu_perm, client_factory))
            registered.append(PERM_NAME)
        except Exception as e:
            logger.warning("Failed to register perm tools: %s", e)

    if enabled.get("urgent"):
        try:
            from .urgent_handler import TOOL_NAME as URG_NAME, TOOL_DESCRIPTION as URG_DESC, TOOL_SCHEMA as URG_SCHEMA, run_feishu_urgent
            registry.register(LarkTool(URG_NAME, URG_DESC, URG_SCHEMA, run_feishu_urgent, client_factory))
            registered.append(URG_NAME)
        except Exception as e:
            logger.warning("Failed to register urgent tools: %s", e)

    if enabled.get("reactions"):
        try:
            from .reactions_handler import TOOL_NAME as REACT_NAME, TOOL_DESCRIPTION as REACT_DESC, TOOL_SCHEMA as REACT_SCHEMA, run_feishu_reactions
            registry.register(LarkTool(REACT_NAME, REACT_DESC, REACT_SCHEMA, run_feishu_reactions, client_factory))
            registered.append(REACT_NAME)
        except Exception as e:
            logger.warning("Failed to register reactions tools: %s", e)

    if enabled.get("calendar"):
        try:
            from .calendar_handler import TOOL_NAME as CAL_NAME, TOOL_DESCRIPTION as CAL_DESC, TOOL_SCHEMA as CAL_SCHEMA, run_feishu_calendar
            registry.register(LarkTool(CAL_NAME, CAL_DESC, CAL_SCHEMA, run_feishu_calendar, client_factory))
            registered.append(CAL_NAME)
        except Exception as e:
            logger.warning("Failed to register calendar tools: %s", e)

    # ── Multi-tool groups (each tool_def in _TOOLS list becomes a separate Tool) ──

    if enabled.get("bitable"):
        try:
            from .bitable_handler import _TOOLS as BITABLE_TOOLS, _dispatch as bitable_dispatch
            for tool_def in BITABLE_TOOLS:
                name = tool_def["name"]
                # Capture name in closure for the handler
                def _make_bitable_handler(n: str):
                    async def handler(params: dict[str, Any], client: Any) -> dict[str, Any]:
                        return await bitable_dispatch(n, params, client)
                    return handler
                registry.register(LarkTool(name, tool_def["description"], tool_def["schema"], _make_bitable_handler(name), client_factory))
                registered.append(name)
        except Exception as e:
            logger.warning("Failed to register bitable tools: %s", e)

    if enabled.get("task"):
        try:
            from .task_handler import _TOOLS as TASK_TOOLS, _dispatch as task_dispatch
            for tool_def in TASK_TOOLS:
                name = tool_def["name"]
                def _make_task_handler(n: str):
                    async def handler(params: dict[str, Any], client: Any) -> dict[str, Any]:
                        return await task_dispatch(n, params, client)
                    return handler
                registry.register(LarkTool(name, tool_def["description"], tool_def["schema"], _make_task_handler(name), client_factory))
                registered.append(name)
        except Exception as e:
            logger.warning("Failed to register task tools: %s", e)

    if registered:
        logger.info("Registered %d Lark tools: %s", len(registered), ", ".join(registered))
    else:
        logger.warning("No Lark tools were registered")
