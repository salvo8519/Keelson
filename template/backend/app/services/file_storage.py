"""Storage of file contents: one interface, two interchangeable backends.

Keelson: upstream stored chat files on the local disk only. Documents and chat files are now
stored objects (``app/services/stored_object.py``): the database holds their owner, size,
SHA-256 and the backend and key of their bytes; this module moves the bytes.

* ``LocalFileStorage`` writes under ``MEDIA_DIR`` (development, single server).
* ``S3FileStorage`` writes to any S3-compatible service: Garage (the default of the Compose
  stacks), AWS S3, Cloudflare R2, Ceph. Large objects are sent as multipart uploads.

Contents are streamed in chunks: the SHA-256 is computed while writing, and no backend loads a
whole object in memory. Credentials come from the settings only and are never logged.
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import shutil
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, ClassVar, Literal, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "text/plain", "text/markdown", "text/csv", "text/html", "text/css",
    "text/xml", "text/x-python", "text/javascript", "text/x-yaml",
    "application/json", "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-yaml",
}

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

StorageBackendName = Literal["local", "s3"]
STORAGE_BACKENDS: tuple[StorageBackendName, ...] = ("local", "s3")

# Size of the chunks read from an upload or a stored object.
CHUNK_SIZE = 1024 * 1024
# Size of the parts of an S3 multipart upload (S3 requires at least 5 MiB but for the last).
# Objects smaller than one part are written with a single request.
S3_PART_SIZE = 8 * 1024 * 1024


def classify_file(mime_type: str, filename: str) -> str:
    """Classify file type based on MIME type and extension."""
    if mime_type in IMAGE_MIME_TYPES:
        return "image"
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return "pdf"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "docx" or "wordprocessingml" in mime_type:
        return "docx"
    return "text"


_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.\-]+")


def _sanitize_filename(filename: str) -> str:
    """Strip path separators, NULL bytes, and unsafe chars from a filename.

    The result is always a single path component with no traversal segments.
    Empty results fall back to ``"file"`` to preserve a non-empty name.
    """
    base = Path(filename).name.replace("\x00", "")
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", base).strip("._")
    return cleaned or "file"


def make_storage_filename(filename: str) -> str:
    """Create a unique storage filename to prevent collisions and path traversal."""
    safe = _sanitize_filename(filename)
    return f"{uuid.uuid4().hex[:12]}_{safe}"


# --- Streams -------------------------------------------------------------------------------


class ObjectTooLargeError(ValueError):
    """The content exceeds the size allowed for it; nothing is kept."""

    def __init__(self, max_size: int) -> None:
        super().__init__(f"content larger than {max_size} bytes")
        self.max_size = max_size


class AsyncReadable(Protocol):
    """What an upload offers (``fastapi.UploadFile`` among others)."""

    async def read(self, size: int = -1) -> bytes: ...


async def iter_bytes(data: bytes, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
    """Content already in memory, as a stream."""
    for start in range(0, len(data), chunk_size):
        yield data[start : start + chunk_size]


async def iter_readable(source: AsyncReadable, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
    """An upload, chunk by chunk (the whole file is never read at once)."""
    while chunk := await source.read(chunk_size):
        yield chunk


@dataclass(frozen=True)
class WrittenObject:
    """What a backend wrote: the size and the SHA-256 of the bytes it received."""

    size: int
    sha256: str


class _Meter:
    """Counts and hashes a stream while it is written, and enforces its limit."""

    def __init__(self, max_size: int | None) -> None:
        self.size = 0
        self.max_size = max_size
        self._hash = hashlib.sha256()

    def add(self, chunk: bytes) -> None:
        self.size += len(chunk)
        if self.max_size is not None and self.size > self.max_size:
            raise ObjectTooLargeError(self.max_size)
        self._hash.update(chunk)

    def result(self) -> WrittenObject:
        return WrittenObject(size=self.size, sha256=self._hash.hexdigest())


# --- Backends ------------------------------------------------------------------------------


def _open(path: Path, mode: Literal["rb", "wb"]) -> BinaryIO:
    return path.open(mode)


def _next_page(pages: Iterator[dict[str, Any]]) -> dict[str, Any] | None:
    return next(pages, None)


class BaseFileStorage(ABC):
    """A place where contents are written under a key and read back."""

    name: ClassVar[StorageBackendName]

    @abstractmethod
    async def write(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        *,
        content_type: str | None = None,
        max_size: int | None = None,
    ) -> WrittenObject:
        """Write a stream under ``key``. Nothing remains if the stream fails or is too large."""

    @abstractmethod
    def read(self, key: str) -> AsyncIterator[bytes]:
        """The content under ``key``, chunk by chunk. ``FileNotFoundError`` when absent."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove ``key``; absent keys are not an error."""

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> int:
        """Remove every key under ``prefix`` (erasure of an owner); returns how many."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Whether ``key`` holds content."""

    @abstractmethod
    def list_keys(self, prefix: str) -> AsyncIterator[tuple[str, datetime]]:
        """Every key under ``prefix`` with the time it was last written (reconciliation)."""

    async def presigned_url(
        self, key: str, *, content_type: str, content_disposition: str, ttl: int
    ) -> str | None:
        """A short-lived URL to read ``key`` directly, when the backend can issue one."""
        return None

    def get_full_path(self, storage_path: str) -> Path | None:
        """Return absolute filesystem path if available (local storage only)."""
        return None  # pragma: no cover

    # Upstream interface, kept for avatars: a key derived from an owner and a file name.

    async def save(self, user_id: str, filename: str, data: bytes) -> str:
        """Save file and return storage path/key."""
        key = f"{_sanitize_filename(user_id)}/{make_storage_filename(filename)}"
        await self.write(key, iter_bytes(data))
        return key

    async def load(self, storage_path: str) -> bytes:
        """Load file bytes by storage path."""
        return b"".join([chunk async for chunk in self.read(storage_path)])


class LocalFileStorage(BaseFileStorage):
    """Store files on local filesystem."""

    name: ClassVar[StorageBackendName] = "local"

    def __init__(self, base_dir: str | Path = "media"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> Path:
        """Resolve a storage path under base_dir, rejecting traversal attempts."""
        base = self.base_dir.resolve()
        candidate = (base / storage_path).resolve()
        if base != candidate and base not in candidate.parents:
            raise ValueError(f"Path escapes storage root: {storage_path}")
        return candidate

    async def write(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        *,
        content_type: str | None = None,
        max_size: int | None = None,
    ) -> WrittenObject:
        target = self._resolve_safe_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Written beside the target and renamed at the end: a reader never sees half a file.
        partial = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
        meter = _Meter(max_size)
        handle = await asyncio.to_thread(_open, partial, "wb")
        try:
            async for chunk in chunks:
                meter.add(chunk)
                await asyncio.to_thread(handle.write, chunk)
            await asyncio.to_thread(handle.close)
            await asyncio.to_thread(os.replace, partial, target)
        except BaseException:
            handle.close()
            partial.unlink(missing_ok=True)
            raise
        return meter.result()

    async def read(self, key: str) -> AsyncIterator[bytes]:
        path = self._resolve_safe_path(key)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {key}")
        handle = await asyncio.to_thread(_open, path, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, CHUNK_SIZE):
                yield chunk
        finally:
            handle.close()

    async def delete(self, key: str) -> None:
        self._resolve_safe_path(key).unlink(missing_ok=True)

    async def delete_prefix(self, prefix: str) -> int:
        directory = self._resolve_safe_path(prefix)
        if directory == self.base_dir.resolve() or not directory.is_dir():
            return 0
        count = sum(1 for path in directory.rglob("*") if path.is_file())
        await asyncio.to_thread(shutil.rmtree, directory)
        return count

    async def exists(self, key: str) -> bool:
        return self._resolve_safe_path(key).is_file()

    async def list_keys(self, prefix: str) -> AsyncIterator[tuple[str, datetime]]:
        directory = self._resolve_safe_path(prefix)
        if not directory.is_dir():
            return
        base = self.base_dir.resolve()
        paths = await asyncio.to_thread(lambda: [p for p in directory.rglob("*") if p.is_file()])
        for path in paths:
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            yield path.relative_to(base).as_posix(), modified

    def get_full_path(self, storage_path: str) -> Path | None:
        """Return absolute filesystem path for local files."""
        try:
            file_path = self._resolve_safe_path(storage_path)
        except ValueError:
            return None
        return file_path if file_path.exists() else None


@dataclass(frozen=True)
class S3Config:
    """Where and how to reach the S3 service (from the settings)."""

    bucket: str
    region: str
    endpoint: str | None = None
    access_key: str = ""
    secret_key: str = ""
    addressing_style: str = "auto"

    def __repr__(self) -> str:  # the secret never reaches a log or a traceback
        return f"S3Config(bucket={self.bucket!r}, endpoint={self.endpoint!r}, region={self.region!r})"


def _is_missing(error: Exception) -> bool:
    code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound"}


class S3FileStorage(BaseFileStorage):
    """Store files in a bucket of an S3-compatible service."""

    name: ClassVar[StorageBackendName] = "s3"

    def __init__(self, config: S3Config, client: Any = None) -> None:
        self.config = config
        self.bucket = config.bucket
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint or None,
                aws_access_key_id=self.config.access_key or None,
                aws_secret_access_key=self.config.secret_key or None,
                region_name=self.config.region,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": self.config.addressing_style},
                    retries={"max_attempts": 5, "mode": "standard"},
                ),
            )
        return self._client

    async def write(
        self,
        key: str,
        chunks: AsyncIterable[bytes],
        *,
        content_type: str | None = None,
        max_size: int | None = None,
    ) -> WrittenObject:
        meter = _Meter(max_size)
        extra = {"ContentType": content_type} if content_type else {}
        buffer = bytearray()
        upload_id: str | None = None
        parts: list[dict[str, Any]] = []
        try:
            async for chunk in chunks:
                meter.add(chunk)
                buffer += chunk
                while len(buffer) >= S3_PART_SIZE:
                    if upload_id is None:
                        created = await asyncio.to_thread(
                            self.client.create_multipart_upload, Bucket=self.bucket, Key=key, **extra
                        )
                        upload_id = created["UploadId"]
                    part, buffer = bytes(buffer[:S3_PART_SIZE]), buffer[S3_PART_SIZE:]
                    parts.append(await self._upload_part(key, upload_id, len(parts) + 1, part))
            if upload_id is None:
                await asyncio.to_thread(
                    self.client.put_object, Bucket=self.bucket, Key=key, Body=bytes(buffer), **extra
                )
            else:
                if buffer:
                    parts.append(await self._upload_part(key, upload_id, len(parts) + 1, bytes(buffer)))
                await asyncio.to_thread(
                    self.client.complete_multipart_upload,
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
        except BaseException:
            if upload_id is not None:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        self.client.abort_multipart_upload, Bucket=self.bucket, Key=key, UploadId=upload_id
                    )
            raise
        return meter.result()

    async def _upload_part(self, key: str, upload_id: str, number: int, data: bytes) -> dict[str, Any]:
        response = await asyncio.to_thread(
            self.client.upload_part,
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=number,
            Body=data,
        )
        return {"PartNumber": number, "ETag": response["ETag"]}

    async def read(self, key: str) -> AsyncIterator[bytes]:
        try:
            response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        except Exception as error:
            if _is_missing(error):
                raise FileNotFoundError(f"Object not found: {key}") from None
            raise
        body = response["Body"]
        try:
            while chunk := await asyncio.to_thread(body.read, CHUNK_SIZE):
                yield chunk
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        def _delete() -> int:
            count = 0
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                keys = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if keys:
                    self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys, "Quiet": True})
                    count += len(keys)
            return count

        return await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)
        except Exception as error:
            if _is_missing(error):
                return False
            raise
        return True

    async def list_keys(self, prefix: str) -> AsyncIterator[tuple[str, datetime]]:
        paginator = self.client.get_paginator("list_objects_v2")
        pages: Iterator[dict[str, Any]] = iter(paginator.paginate(Bucket=self.bucket, Prefix=prefix))
        while page := await asyncio.to_thread(_next_page, pages):
            for item in page.get("Contents", []):
                yield item["Key"], item["LastModified"]

    async def presigned_url(
        self, key: str, *, content_type: str, content_disposition: str, ttl: int
    ) -> str | None:
        # Keelson: the Content-Disposition is built by the caller (app/core/user_content.py).
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": content_disposition,
            },
            ExpiresIn=ttl,
        )


@lru_cache(maxsize=4)
def _s3_storage(config: S3Config) -> S3FileStorage:
    # One client per configuration: boto3 clients are thread-safe and costly to build.
    return S3FileStorage(config)


def s3_config() -> S3Config:
    """The S3 configuration of the settings."""
    return S3Config(
        bucket=settings.S3_BUCKET,
        region=settings.S3_REGION,
        endpoint=settings.S3_ENDPOINT,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        addressing_style=settings.S3_ADDRESSING_STYLE,
    )


def get_file_storage(backend: StorageBackendName | str | None = None) -> BaseFileStorage:
    """The backend named ``backend``, or the one new objects are written to."""
    name = backend or settings.storage_backend
    if name == "local":
        return LocalFileStorage(base_dir=settings.MEDIA_DIR)
    if name == "s3":
        return _s3_storage(s3_config())
    raise ValueError(f"Unknown storage backend: {name}")


# --- Avatars (Keelson) ------------------------------------------------------------------------
# Avatars stay on the local disk under a folder of their owner. The record keeps the path, so
# a path is served or deleted only inside its owner's folder: a value written in the record by
# anything but the upload (upstream let organization admins set ``avatar_url``) cannot reach
# another owner's files.

AVATAR_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
AVATAR_MAX_BYTES = 2 * 1024 * 1024


def avatar_folder(owner: Literal["user", "organization"], owner_id: uuid.UUID) -> str:
    return f"avatars/orgs/{owner_id}" if owner == "organization" else f"avatars/{owner_id}"


def is_inside(folder: str, key: str | None) -> bool:
    """True when ``key`` names a file below ``folder`` (relative, no ``..``)."""
    if not key:
        return False
    path, base = PurePosixPath(key), PurePosixPath(folder)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts) > len(base.parts)
        and path.parts[: len(base.parts)] == base.parts
    )


async def replace_avatar(folder: str, current: str | None, filename: str, data: bytes) -> str:
    """Store a new avatar in ``folder`` and remove the previous one if it is the owner's."""
    storage = get_file_storage("local")
    if is_inside(folder, current):
        with contextlib.suppress(Exception):
            await storage.delete(current)  # type: ignore[arg-type]
    # ``save`` keeps only the last component of its folder argument, which put the file outside
    # ``folder``, where ``avatar_path`` never finds it: the key is built here.
    key = f"{folder}/{make_storage_filename(filename)}"
    await storage.write(key, iter_bytes(data))
    return key


def avatar_path(folder: str, key: str | None) -> str | None:
    """Full path of an avatar inside its owner's folder, or None."""
    if not is_inside(folder, key):
        return None
    full_path = get_file_storage("local").get_full_path(key)  # type: ignore[arg-type]
    return str(full_path) if full_path is not None else None
