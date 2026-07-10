"""
backend/storage/local.py

Local filesystem implementation of StorageBackend.

Files are stored on disk under the configured upload and processed
directories (LOCAL_UPLOAD_DIR and LOCAL_PROCESSED_DIR in .env).

Logical keys are relative paths such as ``uploads/abc123.csv`` or
``processed/abc123_clean.csv``.  The backend resolves these relative to
a configurable root directory (defaults to the project data/ folder).

Activation: STORAGE_BACKEND=local in .env (this is the default).
"""

from __future__ import annotations

import logging
from pathlib import Path

from backend.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    """
    StorageBackend that reads and writes files on the local filesystem.

    All keys are treated as relative paths under ``root_dir``.  Path
    traversal sequences (``..``) are rejected with :class:`ValueError`.
    """

    def __init__(self, root_dir: str | Path) -> None:
        """
        Args:
            root_dir: Absolute path to the data root directory.
                      Sub-directories (uploads/, processed/) are created
                      automatically on first write.
        """
        self._root = Path(root_dir).resolve()

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    async def save(self, key: str, data: bytes) -> str:
        """Write ``data`` to disk and return the absolute path."""
        dest = self._resolve(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.debug("LocalStorage saved %d B → %s", len(data), dest)
        return str(dest)

    async def load(self, key: str) -> bytes:
        """Read and return the file at ``key``."""
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError(f"LocalStorage: key not found: {key!r}")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        """Remove the file at ``key``; silently ignores missing files."""
        path = self._resolve(key)
        try:
            path.unlink(missing_ok=True)
            logger.debug("LocalStorage deleted: %s", path)
        except Exception as exc:
            logger.warning("LocalStorage delete failed for %s: %s", key, exc)

    async def exists(self, key: str) -> bool:
        """Return True if the file exists on disk."""
        return self._resolve(key).is_file()

    async def url(self, key: str, *, expires_in: int = 3600) -> str:
        """
        Return the absolute filesystem path.

        The ``expires_in`` parameter is accepted for interface compatibility
        but has no effect for local storage.
        """
        return str(self._resolve(key))

    async def health_check(self) -> bool:
        """Return True if the root directory is readable."""
        try:
            return self._root.is_dir()
        except Exception as exc:
            logger.warning("LocalStorage health_check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        """
        Resolve a logical key to an absolute path under root_dir.

        Raises:
            ValueError: If the resolved path escapes the root directory
                        (path traversal attempt).
        """
        if ".." in key or key.startswith("/") or key.startswith("\\"):
            raise ValueError(f"Invalid storage key (path traversal): {key!r}")
        resolved = (self._root / key).resolve()
        if not str(resolved).startswith(str(self._root)):
            raise ValueError(f"Path traversal detected for key: {key!r}")
        return resolved
