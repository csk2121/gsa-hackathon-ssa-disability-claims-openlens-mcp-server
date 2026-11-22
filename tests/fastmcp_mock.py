"""
Mock for fastmcp — allows tests to run in environments where fastmcp is not installed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FastMCP:
    """Minimal FastMCP stub for testing."""

    def __init__(self, name: str = "", version: str = "", instructions: str = "") -> None:
        self.name = name
        self.version = version
        self.instructions = instructions
        self._tools: dict[str, Any] = {}
        self._prompts: dict[str, Any] = {}
        self._resources: dict[str, Any] = {}

    def tool(self, name: str = "", description: str = "") -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._tools[name or fn.__name__] = fn
            return fn
        return decorator

    def prompt(self, name: str = "", description: str = "") -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._prompts[name or fn.__name__] = fn
            return fn
        return decorator

    def resource(
        self,
        uri: str = "",
        name: str = "",
        description: str = "",
        mime_type: str = "",
    ) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._resources[name or fn.__name__] = fn
            return fn
        return decorator

    def run(self) -> None:
        pass
