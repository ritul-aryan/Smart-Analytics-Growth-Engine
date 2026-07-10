"""
backend/sandbox/base.py

CodeExecutor abstract interface.

Defines the contract that every concrete code execution backend must fulfil.
The Custom Visualisation feature (Tab 3 of the dashboard) allows users to
type natural-language chart requests; the LLM generates Python/Plotly code
which is then executed through this interface.

Using an abstraction means:
  - Local dev uses RestrictedPython + AST whitelist (no Docker needed).
  - Production uses an isolated Docker container for true sandboxing.
  - Switching is a one-line config change: SANDBOX_BACKEND=docker.

Current implementations:
  backend/sandbox/restricted.py  — RestrictedPython + AST whitelist (local)
  backend/sandbox/docker.py      — Docker isolated container (cloud)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ExecutionResult:
    """
    Outcome of a sandbox code execution.

    Attributes:
        success:   True if the code ran without errors.
        output:    Any value returned or printed by the code (stringified).
        error:     Error message if success is False, else empty string.
        plotly_fig: Plotly figure dict if the code produced one, else None.
    """

    __slots__ = ("success", "output", "error", "plotly_fig")

    def __init__(
        self,
        *,
        success: bool,
        output: str = "",
        error: str = "",
        plotly_fig: dict[str, Any] | None = None,
    ) -> None:
        self.success = success
        self.output = output
        self.error = error
        self.plotly_fig = plotly_fig

    def __repr__(self) -> str:
        return (
            f"ExecutionResult(success={self.success}, "
            f"error={self.error!r}, has_fig={self.plotly_fig is not None})"
        )


class CodeExecutor(ABC):
    """
    Abstract code execution sandbox.

    All implementations receive a Python code string and a dict of named
    DataFrames available as local variables.  They return an
    :class:`ExecutionResult` — never raise.
    """

    @abstractmethod
    async def execute(
        self,
        code: str,
        dataframes: dict[str, Any] | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> ExecutionResult:
        """
        Execute ``code`` in an isolated environment.

        Args:
            code:            Python source code to run.
            dataframes:      Named pandas DataFrames injected as locals.
                             Keys become variable names inside the code.
            timeout_seconds: Hard execution time limit.  Code exceeding
                             this limit is terminated and an error result
                             is returned.

        Returns:
            :class:`ExecutionResult` — never raises.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Return True if the sandbox backend is ready to execute code.

        For RestrictedPython this is always True (in-process).
        For Docker it checks the Docker daemon is running.
        Must not raise — catch all exceptions and return False.
        """
