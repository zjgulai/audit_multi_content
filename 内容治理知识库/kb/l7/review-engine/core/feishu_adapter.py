#!/usr/bin/env python3
"""Feishu-neutral mapping with a local JSON fallback transport."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROLE_LABELS = {
    "产品负责人": "product",
    "法务": "legal",
    "医学顾问": "medical",
    "北美同事": "north_america",
    "渠道负责人": "channel",
    "Sign-off 负责人": "signoff",
    "内容提交方": "submitter",
    "项目统筹": "project_coordinator",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _idempotency_key(result: Dict[str, Any]) -> str:
    return f"{result.get('review_id', 'review')}:{result.get('content_version', 'unknown')}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def normalize_inbound(event: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Feishu/webhook event into the local review payload shape."""
    fields = dict(event.get("fields") or {})
    payload = dict(event.get("payload") or {})
    payload.update({key: value for key, value in fields.items() if value is not None})
    payload.setdefault("review_id", event.get("review_id") or event.get("event_id") or f"FEISHU-{event.get('message_id', 'event')}")
    payload.setdefault("content_version", "v1")
    payload.setdefault("content_type", "text")
    payload.setdefault("input_manifest", {"status": "pending", "source": event.get("source", "feishu")})
    payload.setdefault("coverage", {})
    payload.setdefault("risk_items", [])
    payload["submission"] = {
        "source": event.get("source", "feishu"),
        "sender_id": event.get("sender_id"),
        "message_id": event.get("message_id"),
        "attachments": event.get("attachments", []),
    }
    return payload


def _mentions(owners: List[str]) -> List[Dict[str, str]]:
    return [
        {"role": ROLE_LABELS.get(owner, owner), "label": owner, "mention_token": f"{{{{role:{ROLE_LABELS.get(owner, owner)}}}}}", "status": "role_placeholder"}
        for owner in owners
    ]


def build_outbound(result: Dict[str, Any], *, report_url: str | None = None) -> Dict[str, Any]:
    owners = list(result.get("next_owners") or [])
    mentions = _mentions(owners)
    mention_text = " ".join(item["mention_token"] for item in mentions)
    summary = result.get("summary", "")
    chat_message = "\n".join(part for part in [summary, f"下一步：{result.get('next_action', '')}", f"责任角色：{', '.join(owners)}", f"SLA：{(result.get('sla') or {}).get('target', '')}", mention_text] if part)
    table_patch = {
        "review_id": result.get("review_id"),
        "content_id": result.get("content_id"),
        "content_version": result.get("content_version"),
        "decision": result.get("decision"),
        "confidence": result.get("confidence"),
        "next_action": result.get("next_action"),
        "next_owners": owners,
        "sla_target": (result.get("sla") or {}).get("target"),
        "report_url": report_url or result.get("report_url"),
        "updated_at": _now(),
        "reviewed_hash": (result.get("version_gate") or {}).get("reviewed_hash"),
        "release_hash": (result.get("version_gate") or {}).get("release_hash"),
    }
    return {
        "adapter_version": "feishu-light-0.1",
        "idempotency_key": _idempotency_key(result),
        "engine_result": result,
        "chat_message": chat_message,
        "report_url": report_url or result.get("report_url"),
        "table_patch": table_patch,
        "mentions": mentions,
        "transport_status": "json_fallback_pending_feishu_credentials",
    }


def write_fallback(outbound: Dict[str, Any], output_dir: str | Path) -> Dict[str, Any]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_filename(outbound['idempotency_key'])}.json"
    if path.exists():
        return {"status": "duplicate", "path": str(path.resolve()), "idempotency_key": outbound["idempotency_key"]}
    path.write_text(json.dumps(outbound, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "written", "path": str(path.resolve()), "idempotency_key": outbound["idempotency_key"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Map a local review result to Feishu-shaped JSON")
    parser.add_argument("result", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-url", default=None)
    args = parser.parse_args()
    result = json.loads(args.result.read_text(encoding="utf-8"))
    print(json.dumps(write_fallback(build_outbound(result, report_url=args.report_url), args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
