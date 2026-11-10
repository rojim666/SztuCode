"""Canonical MCP result with a loss-aware projection for the text runtime."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any


class McpResultValidationError(Exception):
    """Malformed response or violated output contract."""


@dataclass
class McpCallResult:
    content: list[dict[str, Any]] = field(default_factory=list)
    structured_content: dict[str, Any] | None = None
    is_error: bool = False

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> McpCallResult:
        content = response.get("content", [])
        if not isinstance(content, list):
            raise McpResultValidationError("MCP content must be an array")
        for block in content:
            if not isinstance(block, dict) or not isinstance(block.get("type"), str):
                raise McpResultValidationError("MCP content blocks require string type")
            if block["type"] == "text" and not isinstance(block.get("text"), str):
                raise McpResultValidationError("MCP text requires string text")
            if block["type"] == "resource_link" and not isinstance(block.get("uri"), str):
                raise McpResultValidationError("MCP resource_link requires string uri")
        structured = response.get("structuredContent")
        if "structuredContent" in response and not isinstance(structured, dict):
            raise McpResultValidationError("MCP structuredContent must be an object")
        is_error = response.get("isError", False)
        if not isinstance(is_error, bool):
            raise McpResultValidationError("MCP isError must be boolean")
        return cls(copy.deepcopy(content), copy.deepcopy(structured), is_error)

    def as_metadata(self) -> dict[str, object]:
        value: dict[str, object] = {
            "content": copy.deepcopy(self.content), "isError": self.is_error,
        }
        if self.structured_content is not None:
            value["structuredContent"] = copy.deepcopy(self.structured_content)
        return value

    def render_text(self) -> str:
        parts = []
        for block in self.content:
            kind = block["type"]
            if kind == "text":
                parts.append(block["text"])
            elif kind == "resource_link":
                parts.append(f"[MCP resource link: {block.get('name', 'resource')}] {block['uri']}")
            else:
                parts.append(f"[MCP content type '{kind}' is not supported by this text runtime]")
        if self.structured_content is not None:
            parts.append("[MCP structuredContent]\n" + json.dumps(
                self.structured_content, ensure_ascii=False, sort_keys=True,
            ))
        return "\n".join(parts) or ("MCP tool reported an error." if self.is_error else "")
