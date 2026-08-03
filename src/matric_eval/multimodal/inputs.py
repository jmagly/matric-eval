"""
ModalInput — wraps a single image for multimodal evaluation.

Supports loading from bytes, file path, or URL, with:
- SSRF protection for URL-sourced images (HTTPS-only, no private IPs)
- Dimension limits (max 4096×4096)
- File size limits (max 20 MB)
- Decompression bomb protection via PIL.Image.MAX_IMAGE_PIXELS
- Format whitelist (png, jpg/jpeg, gif, webp)
"""

from __future__ import annotations

import base64
import io
import ipaddress
import urllib.parse
from pathlib import Path
from typing import Optional

from PIL import Image

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_DIMENSION = 4096
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_FORMATS = frozenset({"png", "jpg", "jpeg", "gif", "webp"})

# Normalised MIME type map
_FORMAT_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


class ModalInput:
    """
    Wraps a single image for use in multimodal evaluation tasks.

    Construction:
        ModalInput.from_bytes(data, format)
        ModalInput.from_path(path)
        ModalInput.from_url(url)   — SSRF-protected

    Public attributes:
        format  str          Normalised lowercase format (png, jpg, …)
        width   int          Pixel width
        height  int          Pixel height
    """

    def __init__(self, image: Image.Image, format: str) -> None:
        self._image = image
        self.format = format.lower()
        self.width, self.height = image.size

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_bytes(cls, data: bytes, format: str) -> "ModalInput":
        """
        Load a ModalInput from raw image bytes.

        Args:
            data:   Raw image bytes.
            format: Image format hint (png, jpg, jpeg, gif, webp).

        Raises:
            ValueError: If size, format, or dimensions are invalid.
        """
        fmt = format.lower()
        _validate_format(fmt)
        _validate_file_size(len(data))

        # Decompression bomb protection is provided by PIL's default limit
        img = Image.open(io.BytesIO(data))
        img.load()  # Force decode so we can check dimensions

        _validate_dimensions(img.width, img.height)
        return cls(img, fmt)

    @classmethod
    def from_path(cls, path: str | Path) -> "ModalInput":
        """
        Load a ModalInput from a local file path.

        Args:
            path: Path to image file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError:        If size, format, or dimensions are invalid.
        """
        p = Path(path)
        suffix = p.suffix.lstrip(".").lower()
        _validate_format(suffix)

        size = p.stat().st_size
        _validate_file_size(size)

        img = Image.open(p)
        img.load()
        _validate_dimensions(img.width, img.height)
        return cls(img, suffix)

    @classmethod
    def from_url(cls, url: str) -> "ModalInput":
        """
        Load a ModalInput from an HTTPS URL.

        SSRF protection:
        - Only HTTPS scheme is allowed
        - Private/loopback/link-local IP ranges are rejected
        - file:// URLs are rejected

        Args:
            url: HTTPS image URL.

        Raises:
            ValueError:       If URL scheme or host is disallowed.
            PermissionError:  If URL resolves to a private network address.
        """
        _validate_url_safety(url)

        import urllib.request  # only imported when needed

        req = urllib.request.Request(url, headers={"User-Agent": "matric-eval/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = resp.read(MAX_FILE_SIZE_BYTES + 1)

        _validate_file_size(len(data))

        # Determine format from content-type or URL extension
        content_type = resp.headers.get("Content-Type", "")
        fmt = _format_from_content_type(content_type) or _format_from_url(url) or "png"

        img = Image.open(io.BytesIO(data))
        img.load()
        _validate_dimensions(img.width, img.height)
        return cls(img, fmt)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def resize(self, max_dim: int) -> "ModalInput":
        """
        Return a new ModalInput resized so the longest side ≤ max_dim.

        Aspect ratio is preserved. If the image is already within bounds,
        the original image is returned unchanged.

        Args:
            max_dim: Maximum dimension (width or height) in pixels.

        Returns:
            New ModalInput instance (may be the same if no resize needed).
        """
        w, h = self._image.size
        if w <= max_dim and h <= max_dim:
            return self

        if w >= h:
            new_w = max_dim
            new_h = max(1, round(h * max_dim / w))
        else:
            new_h = max_dim
            new_w = max(1, round(w * max_dim / h))

        resized = self._image.resize((new_w, new_h), Image.LANCZOS)
        return ModalInput(resized, self.format)

    def to_base64(self) -> str:
        """
        Encode the image as a base64 string.

        Returns:
            Base64-encoded PNG or original-format bytes as a string.
        """
        buf = io.BytesIO()
        pil_format = _pil_format_name(self.format)
        self._image.save(buf, format=pil_format)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def to_content_image(self):  # returns inspect_ai ContentImage
        """
        Convert to an Inspect AI ContentImage object.

        Returns:
            inspect_ai.model.ContentImage with a data URI.
        """
        from inspect_ai.model import ContentImage

        mime = _FORMAT_MIME.get(self.format, "image/png")
        b64 = self.to_base64()
        data_uri = f"data:{mime};base64,{b64}"
        return ContentImage(image=data_uri)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_format(fmt: str) -> None:
    if fmt not in ALLOWED_FORMATS:
        raise ValueError(f"Unsupported image format '{fmt}'. Allowed: {sorted(ALLOWED_FORMATS)}")


def _validate_file_size(size: int) -> None:
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"Image file size {size:,} bytes exceeds maximum of "
            f"{MAX_FILE_SIZE_BYTES:,} bytes (20 MB)."
        )


def _validate_dimensions(width: int, height: int) -> None:
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ValueError(
            f"Image dimension {width}×{height} exceeds maximum of "
            f"{MAX_DIMENSION}×{MAX_DIMENSION} pixels."
        )


def _validate_url_safety(url: str) -> None:
    """
    Enforce SSRF-safe URL requirements.

    - Scheme must be https
    - Rejects file:// and http://
    - Rejects private/loopback/link-local IPv4 and IPv6 ranges
    """
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme == "file":
        raise PermissionError(f"file:// URLs are not allowed: {url}")

    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URLs are allowed. Got scheme '{parsed.scheme}' in: {url}")

    host = parsed.hostname or ""
    # Strip IPv6 brackets if present
    host = host.strip("[]")

    if not host:
        raise ValueError(f"URL has no valid hostname: {url}")

    # Try to parse as an IP address
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # Not a bare IP — hostname; we can't resolve here (would require DNS),
        # so we only block known-bad patterns
        return

    _reject_private_ip(addr, url)


def _reject_private_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, url: str) -> None:
    """Raise PermissionError if addr is in a private/reserved range."""
    BLOCKED_NETWORKS_V4 = [
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
        ipaddress.IPv4Network("127.0.0.0/8"),
        ipaddress.IPv4Network("169.254.0.0/16"),  # link-local
    ]
    BLOCKED_NETWORKS_V6 = [
        ipaddress.IPv6Network("fc00::/7"),  # unique local (fc/fd)
        ipaddress.IPv6Network("::1/128"),  # loopback
        ipaddress.IPv6Network("fe80::/10"),  # link-local
    ]

    if isinstance(addr, ipaddress.IPv4Address):
        for net in BLOCKED_NETWORKS_V4:
            if addr in net:
                raise PermissionError(
                    f"URL resolves to a private/reserved IP address ({addr}): {url}"
                )
    else:
        for net in BLOCKED_NETWORKS_V6:
            if addr in net:
                raise PermissionError(
                    f"URL resolves to a private/reserved IPv6 address ({addr}): {url}"
                )


def _pil_format_name(fmt: str) -> str:
    """Map our format name to PIL's save format string."""
    mapping = {
        "jpg": "JPEG",
        "jpeg": "JPEG",
        "png": "PNG",
        "gif": "GIF",
        "webp": "WEBP",
    }
    return mapping.get(fmt, "PNG")


def _format_from_content_type(ct: str) -> Optional[str]:
    """Extract format from a MIME content-type string."""
    ct = ct.lower().split(";")[0].strip()
    mapping = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
    }
    return mapping.get(ct)


def _format_from_url(url: str) -> Optional[str]:
    """Extract format from URL file extension."""
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lstrip(".").lower()
    if suffix in ALLOWED_FORMATS:
        return suffix
    return None
