#!/usr/bin/env python3
"""Build and fetch an auditable manifest of approved-domain web sources.

This adapter fetches HTML only. It does not download images or videos from a
page; those assets remain inputs for the media adapters. Each fetched page gets
an immutable local snapshot hash and a visible-text snapshot for later replay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen


ALLOWED_HOST = "momcozy.com"
MAX_BYTES = 5_000_000
USER_AGENT = "brand-content-review-agent/0.1 source-snapshot"


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if not value or self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(value)
        self.text_parts.append(value)


def canonical_url(url: str) -> str:
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("only https URLs are allowed")
    host = parsed.hostname.lower().rstrip(".")
    if host != ALLOWED_HOST and not host.endswith("." + ALLOWED_HOST):
        raise ValueError(f"host_not_allowed:{host}")
    return urlunparse(("https", host, parsed.path or "/", "", "", ""))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_record(candidate: Dict[str, Any]) -> Dict[str, Any]:
    url = candidate["url"]
    return {
        "source_id": candidate["candidate_id"],
        "publisher": "Momcozy",
        "canonical_url": canonical_url(url),
        "discovered_url": url,
        "locator": candidate.get("evidence_scope", ""),
        "scope": {
            "model": candidate.get("model"),
            "product_line": candidate.get("product_line"),
            "channel": candidate.get("channel"),
            "content_type": candidate.get("content_type"),
        },
        "effective_from": None,
        "review_by": None,
        "retrieved_at": None,
        "snapshot_sha256": None,
        "snapshot_path": None,
        "text_snapshot_path": None,
        "status": "draft",
        "approval_status": "discovery_only",
        "fetch_status": "pending",
        "owner": "product+legal",
    }


def build_manifest(candidate_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert source-candidates.json into a stable, fetchable manifest."""
    candidates = candidate_payload.get("candidates") or []
    return {
        "manifest_version": f"momcozy-source-manifest-{datetime.now(timezone.utc).date().isoformat()}",
        "status": "discovery_only",
        "source_policy": "Fetched pages are discovery evidence until product/legal owners approve facts and permitted wording.",
        "sources": [_candidate_record(candidate) for candidate in candidates],
    }


def fetch_source(source: Dict[str, Any], snapshot_dir: str | Path, *, timeout: int = 20) -> Dict[str, Any]:
    """Fetch one HTML page and write raw/text snapshots; return an updated record."""
    output = dict(source)
    root = Path(snapshot_dir)
    root.mkdir(parents=True, exist_ok=True)
    try:
        url = canonical_url(source["canonical_url"])
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        with urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            http_status = getattr(response, "status", None)
            response_type = response.headers.get_content_type()
        if len(body) > MAX_BYTES:
            raise ValueError(f"response_too_large:{MAX_BYTES}")
        digest = _sha256(body)
        stem = f"{source['source_id']}-{digest[:12]}"
        raw_path = root / f"{stem}.html"
        text_path = root / f"{stem}.txt"
        raw_path.write_bytes(body)
        parser = _VisibleTextParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        visible_text = "\n".join(parser.text_parts)
        text_path.write_text(visible_text + "\n", encoding="utf-8")
        output.update({
            "canonical_url": url,
            "retrieved_at": _now(),
            "snapshot_sha256": digest,
            "snapshot_path": str(raw_path.resolve()),
            "text_snapshot_path": str(text_path.resolve()),
            "http_status": http_status,
            "response_content_type": response_type,
            "title": " ".join(parser.title_parts)[:300],
            "bytes": len(body),
            "fetch_status": "fetched",
            "fetch_error": None,
        })
    except Exception as exc:  # Preserve failure in the manifest for NEEDS_INPUT routing.
        output.update({"retrieved_at": _now(), "fetch_status": "failed", "fetch_error": str(exc)})
    return output


def fetch_manifest(manifest: Dict[str, Any], snapshot_dir: str | Path) -> Dict[str, Any]:
    output = dict(manifest)
    output["sources"] = [fetch_source(source, snapshot_dir) for source in manifest.get("sources", [])]
    output["fetched_at"] = _now()
    output["status"] = "fetched_with_errors" if any(s.get("fetch_status") != "fetched" for s in output["sources"]) else "fetched"
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or fetch a Momcozy source manifest")
    parser.add_argument("candidate_file", type=Path, help="source-candidates.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    parser.add_argument("--fetch", action="store_true", help="fetch approved-domain HTML pages")
    args = parser.parse_args()
    manifest = build_manifest(json.loads(args.candidate_file.read_text(encoding="utf-8")))
    if args.fetch:
        snapshot_dir = args.snapshot_dir or args.output.parent.parent / "snapshots" / "momcozy"
        manifest = fetch_manifest(manifest, snapshot_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": manifest["status"], "sources": len(manifest["sources"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
