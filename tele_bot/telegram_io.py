"""Telegram edge — downloading raw image bytes for the Bouncer.

The file arrives as a Telegram ``file_id``; this layer fetches the bytes and
nothing more. Validation into ``PhotoMessage`` happens in the agent boundary
before any model sees the data (SPECS/TECH.md: parse at the edge).
"""

import logging
from typing import Protocol

from tele_bot.logging_decorators import log_async_call

logger = logging.getLogger(__name__)


class DownloadableFile(Protocol):
    """The only Telegram ``File`` surface we need."""

    async def download_as_bytearray(self) -> bytearray: ...


class TelegramFileSource(Protocol):
    """The only Telegram ``Bot`` surface we need."""

    async def get_file(self, file_id: str) -> DownloadableFile: ...


@log_async_call(logger)
async def download_photo_bytes(bot: TelegramFileSource, file_id: str) -> bytes:
    """Download the image bytes for ``file_id`` via the Telegram bot object."""
    if not file_id:
        raise ValueError("file_id must not be empty")
    file = await bot.get_file(file_id)
    payload = await file.download_as_bytearray()
    return bytes(payload)


_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
)


def sniff_image_mime(data: bytes) -> str:
    """Best-effort image content-type from the bytes' signature.

    Telegram photo messages don't carry a reliable mime type, and the contract
    (SPECS/TECH.md) demands an ``image/*`` type before anything else touches
    the payload — so we sniff the magic bytes instead of trusting a header.
    Unknown or missing signatures fail loudly here, at the edge.
    """
    for signature, mime_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            # WebP is RIFF....WEBP; the bare RIFF prefix can collide with the
            # WAV container, so confirm the fourcc before claiming it.
            if mime_type == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime_type
    raise ValueError("photo bytes have no recognisable image signature")
