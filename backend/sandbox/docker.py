"""
backend/sandbox/docker.py

Docker isolated container code execution sandbox.

Used for cloud / production deployment.  Each execution spins up a
disposable Docker container, writes the code + serialised DataFrames in,
runs Python, captures stdout and the Plotly figure dict, then removes the
container.

Security model:
  - True process isolation — LLM code cannot access the host filesystem,
    network, or other containers.
  - Resource limits enforced by Docker (memory, CPU) via run options.
  - Container is always removed after execution regardless of outcome.

Prerequisites:
  - Docker daemon running and accessible.
  - ``docker`` Python SDK installed (``pip install docker``).

Activation: SANDBOX_BACKEND=docker in .env.

Note: ``docker`` is an optional dependency.  Import errors are deferred
to runtime so that the application starts without it when
SANDBOX_BACKEND=restricted (the default).
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from backend.sandbox.base import CodeExecutor, ExecutionResult

logger = logging.getLogger(__name__)

_DOCKER_IMAGE = "python:3.11-slim"
_PREINSTALL = "pip install pandas numpy plotly -q"
_MEM_LIMIT = "256m"
_CPU_QUOTA = 50_000  # 50% of one CPU core


class DockerExecutor(CodeExecutor):
    """
    CodeExecutor that runs code inside a disposable Docker container.

    Each call to :meth:`execute` creates a fresh container, runs the
    code, captures output, and removes the container.
    """

    def __init__(self, image: str = _DOCKER_IMAGE) -> None:
        """
        Args:
            image: Docker image to use.  Must have Python 3.11+ available.
        """
        self._image = image

    async def execute(
        self,
        code: str,
        dataframes: dict[str, Any] | None = None,
        *,
        timeout_seconds: float = 30.0,
    ) -> ExecutionResult:
        """Run code inside a Docker container."""
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    self._run_in_container,
                    code,
                    dataframes or {},
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                error=f"Docker execution timed out after {timeout_seconds}s.",
            )
        except Exception as exc:
            return ExecutionResult(success=False, error=str(exc))

    def _run_in_container(
        self,
        code: str,
        dataframes: dict[str, Any],
    ) -> ExecutionResult:
        """Synchronous implementation — runs in a thread pool."""
        try:
            import docker  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "docker SDK is not installed. "
                "Add 'docker' to requirements.txt or switch SANDBOX_BACKEND=restricted."
            ) from exc

        client = docker.from_env()

        # Build a self-contained script that deserialises DataFrames from JSON
        df_json = json.dumps(
            {k: v.to_json(orient="records") for k, v in dataframes.items()}
            if dataframes else {}
        )

        runner = textwrap.dedent(f"""\
            import json, pandas as pd, numpy as np
            try:
                import plotly.graph_objects as go
            except ImportError:
                go = None

            _dfs = json.loads({df_json!r})
            for _k, _v in _dfs.items():
                globals()[_k] = pd.read_json(_v, orient='records')

            fig = None
            {textwrap.indent(code, '            ')}

            if fig is not None and hasattr(fig, 'to_json'):
                print('__PLOTLY_FIG__' + fig.to_json())
        """)

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "runner.py"
            script_path.write_text(runner)

            try:
                container = client.containers.run(
                    self._image,
                    command=["python", "/code/runner.py"],
                    volumes={tmpdir: {"bind": "/code", "mode": "ro"}},
                    mem_limit=_MEM_LIMIT,
                    cpu_quota=_CPU_QUOTA,
                    network_disabled=True,
                    remove=True,
                    stdout=True,
                    stderr=True,
                    detach=False,
                )
                raw: str = container.decode("utf-8") if isinstance(container, bytes) else str(container)
            except Exception as exc:
                return ExecutionResult(success=False, error=str(exc))

        fig_dict: dict[str, Any] | None = None
        output_lines: list[str] = []
        for line in raw.splitlines():
            if line.startswith("__PLOTLY_FIG__"):
                try:
                    fig_dict = json.loads(line[len("__PLOTLY_FIG__"):])
                except json.JSONDecodeError:
                    pass
            else:
                output_lines.append(line)

        return ExecutionResult(
            success=True,
            output="\n".join(output_lines),
            plotly_fig=fig_dict,
        )

    async def health_check(self) -> bool:
        """Return True if the Docker daemon is running."""
        try:
            import docker  # type: ignore[import]
            client = docker.from_env()
            client.ping()
            return True
        except Exception as exc:
            logger.warning("DockerExecutor health_check failed: %s", exc)
            return False
