"""Asset storage and lifetime management for MathOCR.

Manages extracted figures, crops, and embedded images during recognition
and export. Prevents arbitrary server filesystem access by using opaque
random identifiers.
"""

from __future__ import annotations

import io
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass
class Asset:
    """An extracted image asset belonging to a document recognition job."""

    asset_id: str
    data: bytes
    mime_type: str = "image/png"
    width: int = 0
    height: int = 0
    source_page: int | None = None
    bbox: tuple[int, int, int, int] | None = None  # (left, top, right, bottom)
    caption: str | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "source_page": self.source_page,
            "bbox": self.bbox,
            "caption": self.caption,
        }


class AssetStore:
    """Thread-safe in-memory asset registry with bounded capacity and TTL eviction."""

    def __init__(self, ttl_seconds: float = 7200.0, max_assets: int = 500) -> None:
        self._lock = threading.Lock()
        self._assets: dict[str, Asset] = {}
        self._ttl_seconds = ttl_seconds
        self._max_assets = max_assets

    def store_image(
        self,
        image_or_bytes: Image.Image | bytes,
        mime_type: str = "image/png",
        source_page: int | None = None,
        bbox: tuple[int, int, int, int] | None = None,
        caption: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Asset:
        """Store image data and return an Asset with an opaque UUID."""
        with self._lock:
            self._evict_expired()

            if isinstance(image_or_bytes, Image.Image):
                buf = io.BytesIO()
                fmt = "PNG" if "png" in mime_type.lower() else "JPEG"
                image_or_bytes.save(buf, format=fmt, optimize=True)
                data = buf.getvalue()
                width, height = image_or_bytes.size
            else:
                data = image_or_bytes
                try:
                    with Image.open(io.BytesIO(data)) as probe:
                        width, height = probe.size
                except Exception:
                    width, height = (0, 0)

            asset_id = uuid.uuid4().hex
            asset = Asset(
                asset_id=asset_id,
                data=data,
                mime_type=mime_type,
                width=width,
                height=height,
                source_page=source_page,
                bbox=bbox,
                caption=caption,
                metadata=metadata or {},
            )
            self._assets[asset_id] = asset

            # Enforce max capacity
            if len(self._assets) > self._max_assets:
                # Remove oldest
                oldest_id = min(self._assets.keys(), key=lambda k: self._assets[k].created_at)
                self._assets.pop(oldest_id, None)

            return asset

    def get(self, asset_id: str) -> Asset | None:
        """Retrieve an asset by its opaque identifier."""
        if not asset_id or not re.match(r"^[0-9a-fA-F]{16,64}$", asset_id):
            return None
        with self._lock:
            asset = self._assets.get(asset_id)
            if asset and (time.time() - asset.created_at) > self._ttl_seconds:
                self._assets.pop(asset_id, None)
                return None
            return asset

    def remove(self, asset_id: str) -> bool:
        """Remove an asset explicitly."""
        with self._lock:
            return self._assets.pop(asset_id, None) is not None

    def _evict_expired(self) -> None:
        """Remove assets older than TTL."""
        now = time.time()
        expired = [
            aid for aid, a in self._assets.items() if (now - a.created_at) > self._ttl_seconds
        ]
        for aid in expired:
            self._assets.pop(aid, None)

    def clear(self) -> None:
        """Clear all stored assets."""
        with self._lock:
            self._assets.clear()


# Default process-level asset store
default_asset_store = AssetStore()
