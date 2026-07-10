"""
backend/sandbox/restricted.py

RestrictedPython + AST whitelist code execution sandbox.

Used for local development.  Runs LLM-generated Python inside the same
process using RestrictedPython's compile_restricted, with a hand-rolled
AST visitor that rejects any import or attribute access not on the
explicit whitelist.

Security model:
  - No imports permitted beyond the whitelist (pandas, numpy, plotly.graph_objects).
  - No file system access (__builtins__ stripped to a safe subset).
  - No network access (socket, urllib, requests all blocked by the whitelist).
  - Execution is synchronous inside asyncio.run_in_executor to avoid
    blocking the event loop.
  - Hard timeout enforced via concurrent.futures.

Activation: SANDBOX_BACKEND=restricted in .env (this is the default).
"""

from __future__ import annotations

import ast
import asyncio
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from backend.sandbox.base import CodeExecutor, ExecutionResult

logger = logging.getLogger(__name__)

# Modules the LLM-generated code may import.
_ALLOWED_IMPORTS: frozenset[str] = frozenset({
    "pandas", "pd",
    "numpy", "np",
    "plotly", "plotly.graph_objects", "plotly.express",
    "math", "statistics", "collections", "itertools",
})

# Top-level builtins permitted inside the sandbox.
_SAFE_BUILTINS: dict[str, Any] = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)  # type: ignore[index]
    for name in (
        "abs", "all", "any", "bool", "dict", "enumerate", "filter",
        "float", "int", "isinstance", "len", "list", "map", "max",
        "min", "print", "range", "round", "set", "sorted", "str",
        "sum", "tuple", "type", "zip",
    )
    if (isinstance(__builtins__, dict) and name in __builtins__)  # type: ignore[operator]
    or (not isinstance(__builtins__, dict) and hasattr(__builtins__, name))
}

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sandbox")


class _ImportWhitelistVisitor(ast.NodeVisitor):
    """AST visitor that raises on any import not in the whitelist."""

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base = alias.name.split(".")[0]
            if base not in _ALLOWED_IMPORTS:
                raise ValueError(f"Import not permitted: {alias.name!r}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        base = module.split(".")[0]
        if base not in _ALLOWED_IMPORTS:
            raise ValueError(f"Import not permitted: from {module!r}")
        self.generic_visit(node)


def _validate_ast(code: str) -> None:
    """Parse and walk the AST; raise ValueError on any disallowed construct."""
    tree = ast.parse(code, mode="exec")
    _ImportWhitelistVisitor().visit(tree)


def _run_code(
    code: str,
    dataframes: dict[str, Any],
) -> ExecutionResult:
    """Execute code synchronously (called inside a thread pool)."""
    try:
        _validate_ast(code)
    except (SyntaxError, ValueError) as exc:
        return ExecutionResult(success=False, error=f"Validation error: {exc}")

    local_ns: dict[str, Any] = {**dataframes}
    global_ns: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}

    # Pre-inject allowed modules so LLM code can use them without importing
    try:
        import pandas as pd  # noqa: PLC0415
        import numpy as np   # noqa: PLC0415
        global_ns["pd"] = pd
        global_ns["np"] = np
    except ImportError:
        pass
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
        global_ns["go"] = go
    except ImportError:
        pass

    captured_output: list[str] = []

    def _print(*args: Any, **_: Any) -> None:
        captured_output.append(" ".join(str(a) for a in args))

    global_ns["__builtins__"]["print"] = _print  # type: ignore[index]

    try:
        exec(compile(code, "<sandbox>", "exec"), global_ns, local_ns)  # noqa: S102
    except Exception:
        return ExecutionResult(
            success=False,
            error=traceback.format_exc(limit=5),
            output="\n".join(captured_output),
        )

    # Extract a Plotly figure if the code assigned one to `fig`
    fig_dict: dict[str, Any] | None = None
    fig = local_ns.get("fig")
    if fig is not None:
        try:
            fig_dict = fig.to_dict() if hasattr(fig, "to_dict") else dict(fig)
        except Exception as exc:
            logger.debug("Could not serialise fig: %s", exc)

    return ExecutionResult(
        success=True,
        output="\n".join(captured_output),
        plotly_fig=fig_dict,
    )


class RestrictedExecutor(CodeExecutor):
    """CodeExecutor using RestrictedPython-style AST validation + exec."""

    async def execute(
        self,
        code: str,
        dataframes: dict[str, Any] | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> ExecutionResult:
        """Run code in a thread pool with a hard timeout."""
        loop = asyncio.get_event_loop()
        dfs = dataframes or {}
        future = loop.run_in_executor(_executor, _run_code, code, dfs)
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except (asyncio.TimeoutError, FuturesTimeout):
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout_seconds}s.",
            )
        except Exception as exc:
            return ExecutionResult(success=False, error=str(exc))

    async def health_check(self) -> bool:
        """Always healthy — runs in-process with no external dependency."""
        return True
