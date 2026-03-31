"""feishu_doc and feishu_app_scopes action implementations.

Mirrors: clawdbot-feishu/src/doc-tools/actions.ts
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_LEGACY_DOC_RE = re.compile(r"^doccn[a-zA-Z0-9]+$")


def _is_legacy_doc(token: str) -> bool:
    return bool(_LEGACY_DOC_RE.match(token))


async def read_doc(client: Any, doc_token: str) -> dict[str, Any]:
    """Read document title and content."""
    loop = asyncio.get_running_loop()
    if _is_legacy_doc(doc_token):
        return await _read_legacy_doc(client, doc_token)

    from lark_oapi.api.docx.v1 import GetDocumentRequest, ListDocumentBlockRequest

    req = GetDocumentRequest.builder().document_id(doc_token).build()
    resp = await loop.run_in_executor(None, lambda: client.docx.v1.document.get(req))
    if not resp.success():
        raise RuntimeError(f"document.get failed: {resp.msg}, code={resp.code}")
    doc = resp.data.document
    title = getattr(doc, "title", "") or ""

    text_parts: list[str] = []
    block_count = 0
    block_types: list[int] = []
    page_token: str | None = None

    while True:
        builder = ListDocumentBlockRequest.builder().document_id(doc_token).page_size(500)
        if page_token:
            builder = builder.page_token(page_token)
        blocks_resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block.list(builder.build()))
        if not blocks_resp.success() or not blocks_resp.data:
            break
        for block in (blocks_resp.data.items or []):
            block_type = getattr(block, "block_type", 0)
            block_count += 1
            block_types.append(block_type)
            _extract_block_text(block, block_type, text_parts)
        page_token = getattr(blocks_resp.data, "page_token", None)
        if not page_token or not getattr(blocks_resp.data, "has_more", False):
            break

    return {
        "document_id": doc_token,
        "title": title,
        "content": "".join(text_parts).strip(),
        "block_count": block_count,
        "hint": "Use 'list_blocks' to see block IDs for fine-grained editing.",
    }


async def _read_legacy_doc(client: Any, doc_token: str) -> dict[str, Any]:
    """Read a legacy doc format via raw content API."""
    loop = asyncio.get_running_loop()
    import lark_oapi as lark

    req = lark.RawRequestOpts(
        method="GET",
        url=f"/open-apis/doc/v2/{doc_token}/raw_content",
        access_token_type=lark.AccessTokenType.TENANT,
    )
    resp = await loop.run_in_executor(None, lambda: client.request(req))
    if not getattr(resp, "success", lambda: True)():
        raise RuntimeError(f"legacy doc read failed: {resp.msg}")
    content = getattr(resp.data, "content", "") or ""
    return {"document_id": doc_token, "content": content, "format": "doc", "hint": "Legacy doc format."}


def _extract_block_text(block: Any, block_type: int, parts: list[str]) -> None:
    """Extract readable text from a block object and append to parts.

    Block type reference (lark-oapi docx.v1):
        1=page, 2=text(paragraph), 3-11=heading1-9, 12=bullet, 13=ordered,
        14=code, 15=quote, 17=todo, 22=divider, 23=image, 27=table,
        31=callout, ...
    The SDK attribute names: block.text (not .paragraph), block.bullet,
    block.ordered, block.todo, block.code, block.quote, block.callout, etc.
    """
    def _text_from_elements(elements: list) -> str:
        result = ""
        for elem in (elements or []):
            tr = getattr(elem, "text_run", None)
            if tr:
                result += getattr(tr, "content", "") or ""
            # Also handle mention_doc, mention_user, equation inline elements
            me = getattr(elem, "mention_doc", None)
            if me:
                result += getattr(me, "title", "") or "[doc]"
            mu = getattr(elem, "mention_user", None)
            if mu:
                result += getattr(mu, "user_id", "") or "@user"
            eq = getattr(elem, "equation", None)
            if eq:
                result += getattr(eq, "content", "") or "[equation]"
        return result

    def _get_elements(obj: Any) -> list:
        """Get elements from a block content object (text, bullet, ordered, etc.)."""
        return getattr(obj, "elements", None) or []

    if block_type == 2:  # text (paragraph)
        text_obj = getattr(block, "text", None)
        text = _text_from_elements(_get_elements(text_obj)) if text_obj else ""
        parts.append(text + "\n")
    elif 3 <= block_type <= 11:  # heading1–heading9
        level = block_type - 2
        for i in range(1, 10):
            h = getattr(block, f"heading{i}", None)
            if h:
                text = _text_from_elements(_get_elements(h))
                parts.append(f"{'#' * level} {text}\n")
                break
    elif block_type == 12:  # bullet list item
        bullet = getattr(block, "bullet", None)
        if bullet:
            text = _text_from_elements(_get_elements(bullet))
            parts.append(f"- {text}\n")
    elif block_type == 13:  # ordered list item
        ordered = getattr(block, "ordered", None)
        if ordered:
            text = _text_from_elements(_get_elements(ordered))
            parts.append(f"1. {text}\n")
    elif block_type == 14:  # code
        code = getattr(block, "code", None)
        if code:
            lang = getattr(code, "language", "") or ""
            text = _text_from_elements(_get_elements(code))
            parts.append(f"```{lang}\n{text}\n```\n")
    elif block_type == 15:  # quote
        quote = getattr(block, "quote", None)
        if quote:
            text = _text_from_elements(_get_elements(quote))
            parts.append(f"> {text}\n")
    elif block_type == 17:  # todo / checkbox
        todo = getattr(block, "todo", None)
        if todo:
            text = _text_from_elements(_get_elements(todo))
            done = getattr(todo, "style", None)
            checked = getattr(done, "done", False) if done else False
            marker = "[x]" if checked else "[ ]"
            parts.append(f"- {marker} {text}\n")
    elif block_type == 22:  # divider
        parts.append("---\n")
    elif block_type == 23:  # image
        image = getattr(block, "image", None)
        if image:
            token = getattr(image, "token", "") or ""
            parts.append(f"[Image: {token}]\n")
    elif block_type == 27:  # table
        table = getattr(block, "table", None)
        if table:
            rows = getattr(table, "property", None)
            row_count = getattr(rows, "row_size", "?") if rows else "?"
            col_count = getattr(rows, "column_size", "?") if rows else "?"
            parts.append(f"[Table: {row_count}x{col_count}]\n")
    elif block_type == 31:  # callout
        callout = getattr(block, "callout", None)
        if callout:
            # Callout is a container — its children are separate blocks
            parts.append("[Callout]\n")
    elif block_type == 34:  # quote_container
        parts.append("")  # container, children are separate blocks


async def list_blocks(client: Any, doc_token: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    from lark_oapi.api.docx.v1 import ListDocumentBlockRequest

    blocks = []
    page_token: str | None = None
    while True:
        builder = ListDocumentBlockRequest.builder().document_id(doc_token).page_size(500)
        if page_token:
            builder = builder.page_token(page_token)
        resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block.list(builder.build()))
        if not resp.success():
            raise RuntimeError(f"document_block.list failed: {resp.msg}, code={resp.code}")
        for b in (resp.data.items or []):
            text_parts: list[str] = []
            _extract_block_text(b, getattr(b, "block_type", 0), text_parts)
            blocks.append({
                "block_id": getattr(b, "block_id", ""),
                "block_type": getattr(b, "block_type", 0),
                "parent_id": getattr(b, "parent_id", ""),
                "children": getattr(b, "children", []) or [],
                "text": "".join(text_parts).strip(),
            })
        page_token = getattr(resp.data, "page_token", None)
        if not page_token or not getattr(resp.data, "has_more", False):
            break
    return {"blocks": blocks, "total": len(blocks)}


async def get_block(client: Any, doc_token: str, block_id: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    from lark_oapi.api.docx.v1 import GetDocumentBlockRequest

    req = GetDocumentBlockRequest.builder().document_id(doc_token).block_id(block_id).build()
    resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block.get(req))
    if not resp.success():
        raise RuntimeError(f"document_block.get failed: {resp.msg}, code={resp.code}")
    b = resp.data.block
    return {
        "block_id": getattr(b, "block_id", ""),
        "block_type": getattr(b, "block_type", 0),
        "parent_id": getattr(b, "parent_id", ""),
        "children": getattr(b, "children", []) or [],
    }


async def update_block(client: Any, doc_token: str, block_id: str, content: str) -> dict[str, Any]:
    """Replace text content of a block."""
    loop = asyncio.get_running_loop()
    from lark_oapi.api.docx.v1 import PatchDocumentBlockRequest, PatchDocumentBlockRequestBody
    from lark_oapi.api.docx.v1.model import UpdateTextElementsOfBlockRequest, TextElement, TextRun

    text_run = TextRun.builder().content(content).build()
    elem = TextElement.builder().text_run(text_run).build()
    update = UpdateTextElementsOfBlockRequest.builder().elements([elem]).build()

    req = (
        PatchDocumentBlockRequest.builder()
        .document_id(doc_token)
        .block_id(block_id)
        .request_body(
            PatchDocumentBlockRequestBody.builder().update_text_elements(update).build()
        )
        .build()
    )
    resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block.patch(req))
    if not resp.success():
        raise RuntimeError(f"document_block.patch failed: {resp.msg}, code={resp.code}")
    return {"success": True, "block_id": block_id}


async def delete_block(client: Any, doc_token: str, block_id: str) -> dict[str, Any]:
    """Delete a block by removing it from its parent's children."""
    loop = asyncio.get_running_loop()
    from lark_oapi.api.docx.v1 import (
        GetDocumentBlockRequest,
        GetDocumentBlockChildrenRequest,
        BatchDeleteDocumentBlockChildrenRequest,
        BatchDeleteDocumentBlockChildrenRequestBody,
    )

    # Get block to find parent
    b_req = GetDocumentBlockRequest.builder().document_id(doc_token).block_id(block_id).build()
    b_resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block.get(b_req))
    if not b_resp.success():
        raise RuntimeError(f"get_block failed: {b_resp.msg}, code={b_resp.code}")
    parent_id = getattr(b_resp.data.block, "parent_id", doc_token) or doc_token

    # Get parent's children to find index
    ch_req = GetDocumentBlockChildrenRequest.builder().document_id(doc_token).block_id(parent_id).build()
    ch_resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block_children.get(ch_req))
    if not ch_resp.success():
        raise RuntimeError(f"get_block_children failed: {ch_resp.msg}, code={ch_resp.code}")
    children_ids = [getattr(c, "block_id", "") for c in (ch_resp.data.items or [])]
    if block_id not in children_ids:
        raise RuntimeError(f"block {block_id} not found in parent {parent_id}")
    idx = children_ids.index(block_id)

    del_req = (
        BatchDeleteDocumentBlockChildrenRequest.builder()
        .document_id(doc_token)
        .block_id(parent_id)
        .request_body(
            BatchDeleteDocumentBlockChildrenRequestBody.builder()
            .start_index(idx)
            .end_index(idx + 1)
            .build()
        )
        .build()
    )
    del_resp = await loop.run_in_executor(None, lambda: client.docx.v1.document_block_children.batch_delete(del_req))
    if not del_resp.success():
        raise RuntimeError(f"batch_delete failed: {del_resp.msg}, code={del_resp.code}")
    return {"success": True, "deleted_block_id": block_id}


async def list_comments(
    client: Any, doc_token: str, page_token: str | None = None, page_size: int = 50
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    from lark_oapi.api.drive.v1 import ListFileCommentRequest

    builder = (
        ListFileCommentRequest.builder()
        .file_token(doc_token)
        .file_type("docx")
        .page_size(min(page_size, 100))
    )
    if page_token:
        builder = builder.page_token(page_token)
    req = builder.build()
    resp = await loop.run_in_executor(None, lambda: client.drive.v1.file_comment.list(req))
    if not resp.success():
        raise RuntimeError(f"file_comment.list failed: {resp.msg}, code={resp.code}")
    comments = []
    for c in (resp.data.items or []):
        comments.append({
            "comment_id": getattr(c, "comment_id", ""),
            "user_id": getattr(c, "user_id", ""),
            "create_time": getattr(c, "create_time", 0),
            "update_time": getattr(c, "update_time", 0),
            "is_solved": getattr(c, "is_solved", False),
            "reply_count": len(getattr(c, "reply_list", {}).get("replies", []) if isinstance(getattr(c, "reply_list", None), dict) else getattr(getattr(c, "reply_list", None), "replies", []) or []),
        })
    return {
        "comments": comments,
        "has_more": getattr(resp.data, "has_more", False),
        "page_token": getattr(resp.data, "page_token", "") or "",
    }


async def create_comment(client: Any, doc_token: str, content: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    from lark_oapi.api.drive.v1 import CreateFileCommentRequest, CreateFileCommentRequestBody
    from lark_oapi.api.drive.v1.model import FileComment, ReplyList, Reply, ReplyContent, RichTextElement

    text_elem = RichTextElement.builder().type("text_run").text_run({"text": content}).build()
    reply_content = ReplyContent.builder().elements([text_elem]).build()
    reply = Reply.builder().content(reply_content).build()
    reply_list = ReplyList.builder().replies([reply]).build()
    comment = FileComment.builder().reply_list(reply_list).build()

    req = (
        CreateFileCommentRequest.builder()
        .file_token(doc_token)
        .file_type("docx")
        .request_body(CreateFileCommentRequestBody.builder().comment(comment).build())
        .build()
    )
    resp = await loop.run_in_executor(None, lambda: client.drive.v1.file_comment.create(req))
    if not resp.success():
        raise RuntimeError(f"file_comment.create failed: {resp.msg}, code={resp.code}")
    c = resp.data.comment
    return {
        "comment_id": getattr(c, "comment_id", ""),
        "is_solved": getattr(c, "is_solved", False),
    }


async def get_comment(client: Any, doc_token: str, comment_id: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    from lark_oapi.api.drive.v1 import GetFileCommentRequest

    req = (
        GetFileCommentRequest.builder()
        .file_token(doc_token)
        .file_type("docx")
        .comment_id(comment_id)
        .build()
    )
    resp = await loop.run_in_executor(None, lambda: client.drive.v1.file_comment.get(req))
    if not resp.success():
        raise RuntimeError(f"file_comment.get failed: {resp.msg}, code={resp.code}")
    c = resp.data.comment
    return {
        "comment_id": getattr(c, "comment_id", ""),
        "user_id": getattr(c, "user_id", ""),
        "create_time": getattr(c, "create_time", 0),
        "is_solved": getattr(c, "is_solved", False),
    }


async def list_comment_replies(
    client: Any, doc_token: str, comment_id: str, page_token: str | None = None, page_size: int = 50
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    from lark_oapi.api.drive.v1 import ListFileCommentReplyRequest

    builder = (
        ListFileCommentReplyRequest.builder()
        .file_token(doc_token)
        .file_type("docx")
        .comment_id(comment_id)
        .page_size(min(page_size, 100))
    )
    if page_token:
        builder = builder.page_token(page_token)
    req = builder.build()
    resp = await loop.run_in_executor(None, lambda: client.drive.v1.file_comment_reply.list(req))
    if not resp.success():
        raise RuntimeError(f"file_comment_reply.list failed: {resp.msg}, code={resp.code}")
    replies = []
    for r in (resp.data.items or []):
        replies.append({
            "reply_id": getattr(r, "reply_id", ""),
            "user_id": getattr(r, "user_id", ""),
            "create_time": getattr(r, "create_time", 0),
        })
    return {
        "replies": replies,
        "has_more": getattr(resp.data, "has_more", False),
        "page_token": getattr(resp.data, "page_token", "") or "",
    }


async def list_app_scopes(client: Any) -> dict[str, Any]:
    """List granted and pending OAuth scopes for the current app."""
    loop = asyncio.get_running_loop()
    try:
        from lark_oapi.api.application.v6 import ListScopeRequest
        req = ListScopeRequest.builder().build()
        resp = await loop.run_in_executor(None, lambda: client.application.v6.scope.list(req))
        if not resp.success():
            raise RuntimeError(f"scope.list failed: {resp.msg}, code={resp.code}")
        granted = [getattr(s, "scope", s) for s in (getattr(resp.data, "granted_scopes", None) or [])]
        pending = [getattr(s, "scope", s) for s in (getattr(resp.data, "pending_scopes", None) or [])]
        return {
            "granted": granted,
            "pending": pending,
            "summary": f"{len(granted)} granted, {len(pending)} pending",
        }
    except ImportError:
        return {"error": "feishu_app_scopes requires lark_oapi >= 1.x with application.v6 support"}
