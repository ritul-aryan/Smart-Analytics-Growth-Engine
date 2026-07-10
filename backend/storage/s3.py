"""
backend/storage/s3.py

AWS S3 implementation of StorageBackend.

Used for cloud / production deployment.  Files are stored as S3 objects
under the configured bucket (AWS_BUCKET_NAME in .env).

Driver: boto3 with aiobotocore for async I/O.

Activation: STORAGE_BACKEND=s3 in .env.

Note: boto3 / aiobotocore are optional dependencies.  Import errors are
deferred to runtime so that the application starts without them when
STORAGE_BACKEND=local (the default).
"""

from __future__ import annotations

import logging
from typing import Any

from backend.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class S3StorageBackend(StorageBackend):
    """
    StorageBackend backed by AWS S3 via aiobotocore.

    All logical keys map 1-to-1 to S3 object keys within the configured
    bucket.  Pre-signed download URLs are generated via the S3 client.
    """

    def __init__(
        self,
        bucket: str,
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
        region_name: str = "us-east-1",
    ) -> None:
        """
        Args:
            bucket:               S3 bucket name.
            aws_access_key_id:    AWS access key.  Falls back to IAM role
                                  if empty (recommended for EC2/ECS).
            aws_secret_access_key: AWS secret key.
            region_name:          AWS region (default: us-east-1).
        """
        self._bucket = bucket
        self._access_key = aws_access_key_id
        self._secret_key = aws_secret_access_key
        self._region = region_name
        self._client: Any = None  # aiobotocore client, lazily initialised

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    async def save(self, key: str, data: bytes) -> str:
        """Upload ``data`` to S3 and return the S3 URI."""
        client = await self._get_client()
        async with client as s3:
            await s3.put_object(Bucket=self._bucket, Key=key, Body=data)
        uri = f"s3://{self._bucket}/{key}"
        logger.debug("S3Storage saved %d B → %s", len(data), uri)
        return uri

    async def load(self, key: str) -> bytes:
        """Download and return the object at ``key``."""
        client = await self._get_client()
        async with client as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                return await response["Body"].read()
            except Exception as exc:
                if "NoSuchKey" in str(exc) or "404" in str(exc):
                    raise FileNotFoundError(f"S3Storage: key not found: {key!r}") from exc
                raise

    async def delete(self, key: str) -> None:
        """Delete the S3 object at ``key``; silently ignores missing keys."""
        try:
            client = await self._get_client()
            async with client as s3:
                await s3.delete_object(Bucket=self._bucket, Key=key)
            logger.debug("S3Storage deleted: %s", key)
        except Exception as exc:
            logger.warning("S3Storage delete failed for %s: %s", key, exc)

    async def exists(self, key: str) -> bool:
        """Return True if the object exists in S3."""
        try:
            client = await self._get_client()
            async with client as s3:
                await s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    async def url(self, key: str, *, expires_in: int = 3600) -> str:
        """Generate a pre-signed download URL valid for ``expires_in`` seconds."""
        client = await self._get_client()
        async with client as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )

    async def health_check(self) -> bool:
        """Return True if the S3 bucket is accessible."""
        try:
            client = await self._get_client()
            async with client as s3:
                await s3.head_bucket(Bucket=self._bucket)
            return True
        except Exception as exc:
            logger.warning("S3Storage health_check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> Any:
        """Return an aiobotocore S3 client context manager."""
        try:
            import aiobotocore.session  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "aiobotocore is not installed. "
                "Add 'aiobotocore' to requirements.txt or switch STORAGE_BACKEND=local."
            ) from exc

        session = aiobotocore.session.get_session()
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": self._region,
        }
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key

        return session.create_client(**kwargs)
