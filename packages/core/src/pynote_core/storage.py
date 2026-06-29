"""S3-compatible object storage (MinIO in dev, R2/S3 in prod).

Intentionally thin — three operations cover everything M1 needs:
upload bytes, download to path, delete by URI. Presigned URLs and multipart
streaming arrive when files outgrow ~30MB (see PLAN.md).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

import boto3
from botocore.client import Config

from pynote_core.settings import get_settings

if TYPE_CHECKING:
    from pathlib import Path

    from mypy_boto3_s3.client import S3Client


@lru_cache(maxsize=1)
def get_s3_client() -> S3Client:
    settings = get_settings()
    return boto3.client(  # type: ignore[return-value]
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
        ),
    )


def make_uri(key: str) -> str:
    """`s3://bucket/key` form — stored in `source.bytes_uri`."""
    return f"s3://{get_settings().s3_bucket}/{key.lstrip('/')}"


def _split_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got {uri!r}")
    bucket, _, key = uri[len("s3://") :].partition("/")
    if not bucket or not key:
        raise ValueError(f"Malformed s3 URI: {uri!r}")
    return bucket, key


def upload_bytes(key: str, data: bytes, content_type: str | None = None) -> str:
    """Upload bytes; returns the s3:// URI for storage on the Source row."""
    settings = get_settings()
    extra: dict[str, str] = {}
    if content_type:
        extra["ContentType"] = content_type
    get_s3_client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        **extra,  # type: ignore[arg-type]
    )
    return make_uri(key)


def get_object_stream(uri: str) -> tuple[Any, int | None, str | None]:
    """Open an S3 object for streaming. Returns (body, content_length, content_type).

    The returned body is a botocore StreamingBody — iterate it in chunks or hand
    it straight to FastAPI's StreamingResponse.
    """
    bucket, key = _split_uri(uri)
    obj = get_s3_client().get_object(Bucket=bucket, Key=key)
    return obj["Body"], obj.get("ContentLength"), obj.get("ContentType")


def download_to_path(uri: str, dest: Path) -> None:
    bucket, key = _split_uri(uri)
    dest.parent.mkdir(parents=True, exist_ok=True)
    get_s3_client().download_file(bucket, key, str(dest))


def delete(uri: str) -> None:
    bucket, key = _split_uri(uri)
    get_s3_client().delete_object(Bucket=bucket, Key=key)
