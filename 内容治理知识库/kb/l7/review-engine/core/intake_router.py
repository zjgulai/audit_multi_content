#!/usr/bin/env python3
"""Normalize URL, local file, pasted text, and JSON/CSV batch inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse


EXTENSION_TYPES = {
    ".txt": "text", ".md": "text", ".json": "text", ".csv": "text", ".tsv": "text",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".gif": "image",
    ".mp4": "video", ".mov": "video", ".m4v": "video", ".webm": "video",
    ".pdf": "text"
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def infer_content_type(name: str, mime: str | None = None) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in EXTENSION_TYPES:
        return EXTENSION_TYPES[suffix]
    if mime:
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("text/") or mime == "application/pdf":
            return "text"
    return "unknown"


def manifest_from_source(source: Dict[str, Any], *, content_id: str, content_version: str = "v1", **metadata: Any) -> Dict[str, Any]:
    kind = source.get("kind")
    manifest: Dict[str, Any] = {
        "content_id": content_id,
        "content_version": content_version,
        "source_kind": kind,
        "status": "ready",
        "source_ref": None,
        "sha256": None,
        "content_type": "unknown",
        **metadata,
    }
    if kind == "text":
        value = str(source.get("value", ""))
        manifest.update({"source_ref": "inline:text", "sha256": _sha256_bytes(value.encode()), "content_type": "text", "status": "ready" if value else "missing"})
        return manifest
    if kind == "url":
        url = str(source.get("url", ""))
        parsed = urlparse(url)
        manifest.update({"source_ref": url, "content_type": infer_content_type(parsed.path), "status": "url_pending_fetch" if parsed.scheme in {"http", "https"} else "failed"})
        return manifest
    if kind == "file":
        path = Path(str(source.get("path", ""))).expanduser()
        if not path.is_file():
            manifest.update({"source_ref": str(path), "status": "missing"})
            return manifest
        data = path.read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        manifest.update({"source_ref": str(path.resolve()), "sha256": _sha256_bytes(data), "content_type": infer_content_type(path.name, mime), "status": "ready"})
        return manifest
    manifest.update({"status": "failed", "source_ref": str(source)})
    return manifest


def load_batch(path: str | Path) -> List[Dict[str, Any]]:
    """Load rows; each row is later normalized by the caller."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return data["rows"]
        raise ValueError("JSON batch must be an array or an object with rows")
    if p.suffix.lower() in {".csv", ".tsv"}:
        delimiter = "\t" if p.suffix.lower() == ".tsv" else ","
        with p.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle, delimiter=delimiter))
    raise ValueError("batch input must be JSON, CSV, or TSV")


def normalize_batch(path: str | Path) -> List[Dict[str, Any]]:
    manifests = []
    for index, row in enumerate(load_batch(path), start=1):
        source = row.get("source") or ({"kind": "url", "url": row["url"]} if row.get("url") else {"kind": "text", "value": row.get("text", "")})
        manifests.append(manifest_from_source(source, content_id=str(row.get("content_id") or f"batch-{index}"), content_version=str(row.get("content_version") or "v1"), product_line=row.get("product_line"), sku=row.get("sku"), channel=row.get("channel")))
    return manifests
