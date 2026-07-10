"""
backend/storage/base.py

StorageBackend abstract interface.

Defines the contract that every concrete file storage backend must fulfil.
Application code never touches the filesystem or cloud SDK directly — it
works through this interface so that swapping storage is a one-line config
change (STORAGE_BACKEND=s3).

Current implementations:
  backend/storage/local.py  — local filesystem (default, local dev)
  backend/storage/s3.py     — AWS S3 (cloud production)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """
    Abstract file storage backend.

    All methods operate on logical keys (relative path strings such as
    ``uploads/abc123.csv``).  Implementations translate keys to physical
    paths or S3 object keys as appropriate.
    """

    @abstractmethod
    async def save(self, key: str, data: bytes) -> str:
        """
        Persist ``data`` under ``key`` and return the resolved storage path.

        Args:
            key:  Logical file key, e.g. ``uploads/abc123.csv``.
            data: Raw bytes to store.

        Returns:
            The canonical storage reference — an absolute filesystem path
            for the local backend, or an S3 URI (``s3://bucket/key``) for
            the cloud backend.
        """

    @abstractmethod
    async def load(self, key: str) -> bytes:
        """
        Return the raw bytes stored under ``key``.

        Raises:
            FileNotFoundError: If the key does not exist in the backend.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Remove the file at ``key``.

        Silently succeeds if the key does not exist.
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if a file is stored under ``key``, False otherwise."""

    @abstractmethod
    async def url(self, key: str, *, expires_in: int = 3600) -> str:
        """
        Return a URL from which the file can be downloaded.

        For the local backend this is the absolute filesystem path (the
        FastAPI FileResponse endpoint handles serving it).  For S3 this
        is a pre-signed URL valid for ``expires_in`` seconds.

        Args:
            key:        Logical file key.
            expires_in: Presigned URL lifetime in seconds (S3 only).
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Return True if the storage backend is operational.

        Must not raise — catch all exceptions internally and return False.
        """
