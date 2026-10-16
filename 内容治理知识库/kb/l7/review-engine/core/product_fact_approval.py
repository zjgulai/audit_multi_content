#!/usr/bin/env python3
"""Persist product-fact approval events and rebuild the active fact library."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from .product_fact_queue import approved_facts, record_approval
except ImportError:  # direct script execution
    from product_fact_queue import approved_facts, record_approval


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_id(fact_id: str, decision: str, actor: str, role: str, approved_wording: str | None) -> str:
    raw = "|".join([fact_id, decision, actor, role, approved_wording or ""])
    return "EVT-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _write_json(path: str | Path, value: Dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def apply_event(queue: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    """Apply one event once; repeated event IDs are no-ops."""
    event_id = event.get("event_id")
    if not event_id:
        raise ValueError("missing:event_id")
    processed = queue.setdefault("processed_event_ids", [])
    if event_id in processed:
        return queue
    record_approval(
        queue,
        event["fact_id"],
        decision=event["decision"],
        actor=event["actor"],
        role=event["role"],
        approved_wording=event.get("approved_wording"),
        note=event.get("note"),
    )
    processed.append(event_id)
    queue["updated_at"] = _now()
    return queue


def make_event(
    fact_id: str,
    *,
    decision: str,
    actor: str,
    role: str,
    approved_wording: str | None = None,
    note: str | None = None,
) -> Dict[str, Any]:
    return {
        "event_id": _event_id(fact_id, decision, actor, role, approved_wording),
        "fact_id": fact_id,
        "decision": decision,
        "actor": actor,
        "role": role,
        "approved_wording": approved_wording,
        "note": note,
        "recorded_at": _now(),
    }


def rebuild_library(queue: Dict[str, Any], *, source_queue: str | None = None) -> Dict[str, Any]:
    facts: List[Dict[str, Any]] = []
    for entry in approved_facts(queue):
        facts.append({
            "fact_id": entry.get("fact_id"),
            "sku": entry.get("sku"),
            "model": entry.get("model"),
            "product_line": entry.get("product_line"),
            "region": entry.get("region"),
            "kind": entry.get("kind"),
            "fact": entry.get("fact"),
            "value": entry.get("proposed_value"),
            "allowed_wording": entry.get("proposed_allowed_wording"),
            "evidence_refs": entry.get("evidence_refs", []),
            "approvals": entry.get("approvals", []),
        })
    return {
        "library_version": f"momcozy-approved-facts-{datetime.now(timezone.utc).date().isoformat()}",
        "status": "active" if facts else "approval_required",
        "region": "US",
        "approved_facts": facts,
        "pending_queue": source_queue or "knowledge-base/product-fact-approval-queue.json",
        "generated_at": _now(),
        "policy": "Only approved entries with complete evidence and required role approvals are included.",
    }


def persist_approval(
    queue_path: str | Path,
    library_path: str | Path,
    events_path: str | Path,
    event: Dict[str, Any],
) -> Dict[str, Any]:
    queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    events_file = Path(events_path)
    event_log = json.loads(events_file.read_text(encoding="utf-8")) if events_file.is_file() else {"events": []}
    if event["event_id"] not in {item.get("event_id") for item in event_log.get("events", [])}:
        event_log.setdefault("events", []).append(event)
    apply_event(queue, event)
    _write_json(queue_path, queue)
    event_log["updated_at"] = _now()
    _write_json(events_path, event_log)
    library = rebuild_library(queue, source_queue=str(queue_path))
    _write_json(library_path, library)
    return {"queue": queue, "library": library, "events": event_log}


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist one product-fact approval event")
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--fact-id")
    parser.add_argument("--decision", choices=["approved", "rejected", "needs_input"])
    parser.add_argument("--actor")
    parser.add_argument("--role", choices=["product", "legal", "medical"])
    parser.add_argument("--approved-wording")
    parser.add_argument("--note")
    args = parser.parse_args()
    if not args.fact_id:
        queue = json.loads(args.queue.read_text(encoding="utf-8"))
        _write_json(args.library, rebuild_library(queue, source_queue=str(args.queue)))
        print(json.dumps({"status": "synced", "approved_facts": len(approved_facts(queue))}, ensure_ascii=False))
        return
    required = {"decision": args.decision, "actor": args.actor, "role": args.role}
    if any(value is None for value in required.values()):
        parser.error("--fact-id requires --decision, --actor, and --role")
    event = make_event(args.fact_id, decision=args.decision, actor=args.actor, role=args.role, approved_wording=args.approved_wording, note=args.note)
    result = persist_approval(args.queue, args.library, args.events, event)
    print(json.dumps({"event_id": event["event_id"], "fact_status": next(e["status"] for e in result["queue"]["entries"] if e["fact_id"] == args.fact_id), "approved_facts": len(result["library"]["approved_facts"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
