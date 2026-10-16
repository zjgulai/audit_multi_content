#!/usr/bin/env python3
"""Create and update the SKU-level product fact approval queue."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


VALID_DECISIONS = {"approved", "rejected", "needs_input"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _source_lookup(source_manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup = {}
    for source in source_manifest.get("sources", []):
        source_id = source.get("source_id")
        if source_id:
            lookup[source_id] = source
            lookup.setdefault(f"MOM-{source_id}", source)
    return lookup


def _evidence_refs(product: Dict[str, Any], source_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    lookup = _source_lookup(source_manifest)
    refs = []
    for ref in product.get("source_refs", []):
        source_id = ref.get("source_id")
        source = lookup.get(source_id)
        refs.append({
            "source_id": source_id,
            "resolved_source_id": source.get("source_id") if source else None,
            "url": ref.get("url") or (source or {}).get("canonical_url"),
            "locator": ref.get("locator"),
            "snapshot_sha256": (source or {}).get("snapshot_sha256"),
            "snapshot_path": (source or {}).get("snapshot_path"),
            "retrieved_at": (source or {}).get("retrieved_at"),
            "fetch_status": (source or {}).get("fetch_status", "unresolved"),
        })
    return refs


def _has_fetched_evidence(refs: Iterable[Dict[str, Any]]) -> bool:
    return any(ref.get("fetch_status") == "fetched" and ref.get("snapshot_sha256") for ref in refs)


def _claim_roles(claim: str, approval_policy: Dict[str, Any] | None = None) -> List[str]:
    if approval_policy:
        lower = claim.lower()
        tokens = approval_policy.get("health_safety_efficacy_tokens", [])
        if any(token.lower() in lower for token in tokens):
            return list(approval_policy.get("matrix", {}).get("health_safety_efficacy_claim", ["product", "legal", "medical"]))
        return list(approval_policy.get("matrix", {}).get("objective_or_comparative_claim", ["product", "legal"]))
    lower = claim.lower()
    roles = ["product", "legal"]
    if any(token in lower for token in ("health", "medical", "germ", "safe", "feeding", "cross-contamination", "painless", "milk flow", "drainage")):
        roles.append("medical")
    return roles


def _entry(
    product: Dict[str, Any],
    kind: str,
    label: str,
    value: Any,
    evidence_refs: List[Dict[str, Any]],
    index: int,
    role_labels: Dict[str, str],
    approval_policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    required_roles = (
        list((approval_policy or {}).get("matrix", {}).get("verified_fact", ["product"]))
        if kind == "verified_fact"
        else _claim_roles(label, approval_policy)
    )
    evidence_status = "evidence_ready" if _has_fetched_evidence(evidence_refs) else "evidence_gap"
    pending_status = "pending_product_owner" if kind == "verified_fact" else "pending_product_legal_review"
    return {
        "fact_id": f"{product['sku']}:{kind}:{_id(product['sku'], kind, label, value)}",
        "sku": product["sku"],
        "model": product["model"],
        "product_line": product["product_line"],
        "region": product.get("region"),
        "kind": kind,
        "fact": label,
        "proposed_value": value,
        "proposed_allowed_wording": None,
        "evidence_refs": evidence_refs,
        "evidence_status": evidence_status,
        "required_approval_roles": required_roles,
        "approval_route": [{"role": role, "owner_label": role_labels.get(role, role)} for role in required_roles],
        "approvals": [],
        "status": evidence_status if evidence_status == "evidence_gap" else pending_status,
        "source_index": index,
        "created_at": _now(),
        "updated_at": _now(),
        "notes": "官网发现事实；未经 owner 审批不得作为自动 PASS 的产品事实。",
    }


def build_queue(
    seed_products: Dict[str, Any],
    source_manifest: Dict[str, Any],
    routing_policy: Dict[str, Any] | None = None,
    approval_policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Turn pending seed facts and claims into owner-reviewable records."""
    entries: List[Dict[str, Any]] = []
    role_labels = (routing_policy or {}).get("roles", {})
    for product in seed_products.get("products", []):
        refs = _evidence_refs(product, source_manifest)
        for index, fact in enumerate(product.get("verified_facts", []), start=1):
            entries.append(_entry(product, "verified_fact", fact.get("fact", ""), fact.get("value"), refs, index, role_labels, approval_policy))
        offset = len(product.get("verified_facts", []))
        for index, claim in enumerate(product.get("claims_requiring_evidence_or_owner_approval", []), start=offset + 1):
            entries.append(_entry(product, "claim_phrase", claim, None, refs, index, role_labels, approval_policy))
    return {
        "queue_version": f"product-fact-approval-{datetime.now(timezone.utc).date().isoformat()}",
        "status": "pending_owner_approval",
        "knowledge_version": seed_products.get("knowledge_version"),
        "source_manifest_version": source_manifest.get("manifest_version"),
        "routing_version": (routing_policy or {}).get("routing_version"),
        "approval_policy_version": (approval_policy or {}).get("approval_policy_version"),
        "generated_at": _now(),
        "policy": "Only entries with all required role approvals and evidence_ready may enter the approved fact library.",
        "entries": entries,
    }


def record_approval(
    queue: Dict[str, Any],
    fact_id: str,
    *,
    decision: str,
    actor: str,
    role: str,
    approved_wording: str | None = None,
    note: str | None = None,
) -> Dict[str, Any]:
    """Record one role approval and recompute the entry status."""
    if decision not in VALID_DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    for entry in queue.get("entries", []):
        if entry.get("fact_id") != fact_id:
            continue
        if role not in entry.get("required_approval_roles", []):
            raise ValueError(f"role_not_required:{role}")
        entry.setdefault("approvals", []).append({
            "actor": actor,
            "role": role,
            "decision": decision,
            "approved_wording": approved_wording,
            "note": note,
            "recorded_at": _now(),
        })
        if approved_wording:
            entry["proposed_allowed_wording"] = approved_wording
        entry["updated_at"] = _now()
        if decision == "rejected":
            entry["status"] = "rejected"
        elif decision == "needs_input":
            entry["status"] = "needs_input"
        elif all(
            any(a.get("role") == required and a.get("decision") == "approved" for a in entry["approvals"])
            for required in entry.get("required_approval_roles", [])
        ) and entry.get("evidence_status") == "evidence_ready":
            wording = approved_wording or entry.get("proposed_allowed_wording")
            if entry.get("kind") == "claim_phrase" and not wording:
                entry["status"] = "needs_input"
            else:
                entry["status"] = "approved"
                if wording:
                    entry["proposed_allowed_wording"] = wording
        return queue
    raise KeyError(fact_id)


def approved_facts(queue: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [entry for entry in queue.get("entries", []) if entry.get("status") == "approved"]


def product_fact_gate(queue: Dict[str, Any], sku: str, claim: str) -> Dict[str, Any]:
    """Return the product-fact gate result without deciding overall compliance."""
    wanted = str(claim).strip().lower()
    matches = [
        entry for entry in queue.get("entries", [])
        if entry.get("sku") == sku and str(entry.get("fact", "")).strip().lower() == wanted
    ]
    if not matches:
        return {
            "status": "out_of_scope",
            "eligible_for_product_fact_support": False,
            "decision": "REVIEW",
            "owners": ["产品负责人", "法务"],
            "reason": "SKU 没有对应的审批事实记录",
        }
    if any(entry.get("status") == "approved" for entry in matches):
        return {
            "status": "supported",
            "eligible_for_product_fact_support": True,
            "decision": "CONTINUE",
            "owners": [],
            "reason": "已具备所需审批事实；仍需继续检查其他内容风险",
        }
    if any(entry.get("status") == "evidence_gap" for entry in matches):
        owners = [owner["owner_label"] for owner in matches[0].get("approval_route", [])]
        return {
            "status": "evidence_gap",
            "eligible_for_product_fact_support": False,
            "decision": "NEEDS_INPUT",
            "owners": owners or ["产品负责人"],
            "reason": "事实来源没有可用快照或 hash",
        }
    owners = [owner["owner_label"] for owner in matches[0].get("approval_route", [])]
    return {
        "status": "pending_approval",
        "eligible_for_product_fact_support": False,
        "decision": "REVIEW",
        "owners": owners or ["产品负责人"],
        "reason": "事实或允许措辞尚未完成所需 owner 审批",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or update the product fact approval queue")
    parser.add_argument("seed_products", type=Path)
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--routing-policy", type=Path, default=None)
    args = parser.parse_args()
    routing_path = args.routing_policy or args.seed_products.parent / "routing-policy.json"
    routing_policy = json.loads(routing_path.read_text(encoding="utf-8")) if routing_path.exists() else None
    approval_path = args.seed_products.parent / "product-fact-approval-policy.json"
    approval_policy = json.loads(approval_path.read_text(encoding="utf-8")) if approval_path.exists() else None
    queue = build_queue(
        json.loads(args.seed_products.read_text(encoding="utf-8")),
        json.loads(args.source_manifest.read_text(encoding="utf-8")),
        routing_policy,
        approval_policy,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "entries": len(queue["entries"]), "status": queue["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
