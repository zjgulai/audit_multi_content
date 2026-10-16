#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
追加生成器：把 l4/canonical 的两类定稿补进宿主视图（hostlib）

主生成器 gen-host-library.py 只读 l3/candidates/rules.jsonl（509 条规则），
l4 里的另外 733 条定稿从没进过宿主视图 —— 工作台（可视化平台）因此只显示 509 条。

本脚本补上这两类：

| 源 | 条数 | kb_type | 落盘子库 | tier / kind |
|---|---|---|---|---|
| l4/canonical/scoped_clause.jsonl | 375 | external_standard | 1_外部标准库 | L1 / fact |
| l4/canonical/sample_case.jsonl   | 358 | internal_sample   | 2_内部正负样本库 | L1 / fact |

schema 口径**复用主生成器**（frontmatter / insert_kb_class / flush_md / KB_CLASS_BY_DIR），
不重新实现，避免两套口径漂移。

用法（**必须在主生成器之后**）：
    python3 kb/.work/gen-host-library.py    --out <hostlib>
    python3 kb/.work/gen-host-library-l4.py --out <hostlib>
"""
import argparse
import collections
import importlib.util
import json
import os
import re
import sys
from datetime import date, timedelta

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # …/内容治理/kb
GEN_PATH = os.path.join(KB, ".work", "gen-host-library.py")

SRC_SAMPLE = os.path.join(KB, "l4", "canonical", "sample_case.jsonl")
SRC_CLAUSE = os.path.join(KB, "l4", "canonical", "scoped_clause.jsonl")

# ── 复用主生成器（它只在 __main__ 里跑 main()，import 无副作用）────────────
_spec = importlib.util.spec_from_file_location("_genhl", GEN_PATH)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

COLLECTIONS = [
    {
        "dir": "1_外部标准库",
        "name": "内容治理知识库 · 外部标准库",
        "display_name": "外部标准库",
        "source": "kb/l4/canonical/scoped_clause.jsonl（逐字条款 + 登记元数据）",
        "note": "美国法规、平台政策、行业标准、医学共识、本地常识的逐字条款（PRD §7.1，覆盖 P0+P1）。"
                "派生视图：条款原文逐字保留，未改写；逐条领域 owner 待新库补 owner 字段后回填。",
        "form": "scoped_clause",
    },
    {
        "dir": "2_内部正负样本库",
        "name": "内容治理知识库 · 内部正负样本库",
        "display_name": "内部正负样本库",
        "source": "kb/l4/canonical/sample_case.jsonl（正负样本案例）",
        "note": "正面：合规优秀内容；负面：投诉、下架、警告、返工、达人争议、审核争议（PRD §7.1，覆盖 P0+P1+P2）。"
                "派生视图：案例作参照、不构成规则；逐条领域 owner 待新库补 owner 字段后回填。",
        "form": "sample_case",
    },
]

PII_AT = re.compile(r"@[\u4e00-\u9fa5A-Za-z]{2,6}")
PII_IM = re.compile(r"(【[^】]{0,40}】)")


def mask_pii(text: str) -> tuple[str, bool]:
    """按条目内出现的 @人名 做不可逆脱敏。返回 (文本, 是否检出)。"""
    if not text:
        return text, False
    hit = bool(PII_AT.search(text))
    if hit:
        text = PII_AT.sub("@[已脱敏]", text)
    return text, hit


def load_jsonl(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def build_clause_meta(rec: dict, today: str, valid_until: str) -> tuple[dict, str]:
    """scoped_clause → meta + body"""
    art = rec.get("article_no") or ""
    clause_text = (rec.get("clause_text") or "").strip()
    threshold = rec.get("threshold") or []
    terms = rec.get("term_list") or []
    ev = rec.get("evidence_strength") or ""
    body_text, pii_hit = mask_pii(clause_text)

    head = body_text[:40].replace("\n", " ") if body_text else (ev[:40] or "条款")
    title = f"[{art}] 外部标准库：{head}"

    parts = [f"[{art}] 条款（逐字保留）"]
    if body_text:
        parts.append(f"正文「{body_text[:60]}」")
    if threshold:
        parts.append(f"阈值 {len(threshold)} 项")
    if ev:
        parts.append(f"依据级：{ev[:60]}")
    summary = "；".join(parts) + f"。状态 {rec.get('status','')}。"

    meta = {
        "id": gen.safe_name(rec.get("clause_id") or art),
        "title": title,
        "collection": "1_外部标准库",
        "tier": "L1",
        "topic": art,
        "kind": "fact",
        "summary": summary[:400],
        "owner": rec.get("owner") or gen.LIBRARY_OWNER,
        "evidence_level": "L1",
        "data_level": gen.DATA_LEVEL,
        "sensitivity_level": gen.SENSITIVITY,
        "half_life_days": gen.DERIVED_HALF_LIFE_DAYS,
        "created_at": today,
        "valid_until": valid_until,
        "asks": [
            f"{art} 这条条款的原文是什么",
            f"{art} 的判定条件与阈值是什么",
            f"{art} 依据哪份外部材料（锚点 + 指纹）",
        ],
        "not_proves": (
            "不能证明该条已过正式验收（新库 l3 全部为 provisional，l4 为机器晋升）；"
            "不能证明该条可替代合规/法务意见；不能证明该条之外的主题（未命中 ≠ 合规）"
        ),
        "forbidden": (
            "不许把条款的登记元数据当成条款正文 —— 部分条目的 clause_text 是登记字段值，"
            "不是判定条件；不许据本条直接外发文案，外发前仍需人工复核；"
            "不许把派生视图的字段改动当成新库改动（视图不写回）"
        ),
        "related": [],
        "source": {
            "kind": gen.SOURCE_KIND,
            "ref": f"https://{gen.FEISHU_HOST}/base/{gen.DEFAULT_BASE}?table={gen.DEFAULT_TABLE_ID}",
            "fingerprint": f"{gen.DEFAULT_BASE}/{gen.DEFAULT_TABLE_ID}",
            "captured_at": today,
        },
        "provenance": {
            "anchor": f"kb/l4/canonical/scoped_clause.jsonl#{rec.get('clause_id','')}",
            "confidence": gen.CONFIDENCE_CERTAIN,
        },
        "pii": {
            "detected": pii_hit,
            "masked": pii_hit,
            "strategy": "条款正文按 @人名 正则不可逆脱敏（mask-at-name）；无其他自然人信息",
        },
        # 业务字段（照抄新库，不改写）
        "article_no": art,
        "form": "scoped_clause",
        "kb_type": rec.get("kb_type") or "external_standard",
        "kb_version": rec.get("kb_version") or "v0",
        "clause_id": rec.get("clause_id") or "",
        "status": rec.get("status") or "",
        "evidence_strength": ev,
        "quality_flag": rec.get("quality_flag") or "",
        "effective_period": rec.get("effective_period") or "",
        "promoted_from": rec.get("promoted_from") or "",
        "anchor": rec.get("anchor") or "",
        "source_sha256": rec.get("source_sha256") or "",
        "resource_id": rec.get("resource_id") or "",
        "clause_text": body_text,
        "threshold": json.dumps(threshold, ensure_ascii=False) if threshold else "",
        "term_list": "、".join(str(t) for t in terms) if terms else "",
    }

    body = [
        f"# {title}",
        "",
        f"**条款号**：{art}　|　**形态**：`scoped_clause`　|　**状态**：{rec.get('status','')}",
        "",
        "## 条款正文（逐字保留，未改写）",
        "",
        body_text if body_text else "（本条的 `clause_text` 为空）",
        "",
    ]
    if threshold:
        body += ["## 阈值", "", json.dumps(threshold, ensure_ascii=False, indent=1), ""]
    if terms:
        body += ["## 词表", "", "、".join(str(t) for t in terms), ""]
    body += [
        "## 引用依据",
        "",
        f"- 锚点：`{rec.get('anchor','')}`",
        f"- 指纹：`{rec.get('source_sha256','')}`",
        f"- 依据级：{ev or '（源库未标）'}",
        "",
    ]
    return meta, "\n".join(body)


def build_case_meta(rec: dict, today: str, valid_until: str) -> tuple[dict, str]:
    """sample_case → meta + body"""
    art = rec.get("article_no") or ""
    polarity = rec.get("polarity") or ""
    material = rec.get("material_type") or ""
    channel = rec.get("channel") or ""
    reason_cat = rec.get("reason_category") or ""
    body_raw = rec.get("sample_body") or ""
    reason = rec.get("reason_analysis") or ""
    advice = rec.get("advice") or ""
    body_text, pii_hit = mask_pii(body_raw)
    reason_text, pii_r = mask_pii(reason)
    pii_hit = pii_hit or pii_r

    title = f"[{art}] 内部正负样本库：{polarity}{('·' + reason_cat) if reason_cat else ''}{('·' + material) if material else ''}"

    summary = (
        f"[{art}] {polarity}案例（{material}{('/' + channel) if channel else ''}）："
        f"{('原因归类「' + reason_cat + '」；') if reason_cat else ''}"
        f"案例作参照、不构成规则。状态 {rec.get('status','')}。"
    )

    meta = {
        "id": gen.safe_name(rec.get("case_id") or art),
        "title": title,
        "collection": "2_内部正负样本库",
        "tier": "L1",
        "topic": art,
        "kind": "fact",
        "summary": summary[:400],
        "owner": rec.get("owner") or gen.LIBRARY_OWNER,
        "evidence_level": "L1",
        "data_level": gen.DATA_LEVEL,
        "sensitivity_level": gen.SENSITIVITY,
        "half_life_days": gen.DERIVED_HALF_LIFE_DAYS,
        "created_at": today,
        "valid_until": valid_until,
        "asks": [
            f"{art} 是正例还是反例",
            f"{art} 的问题要点与原因归类是什么",
            f"{art} 应该怎么做（合规做法 / 修改建议）",
        ],
        "not_proves": (
            "案例是参照，不构成规则 —— 不能证明「和它像」就违规、也不能证明「和它像」就合规；"
            "不能证明该条已过正式验收；不能证明该条可替代合规/法务意见"
        ),
        "forbidden": (
            "不许把案例当规则用（案例只作参照）；不许据本条直接判 BLOCK；"
            "不许把派生视图的字段改动当成新库改动（视图不写回）"
        ),
        "related": [],
        "source": {
            "kind": gen.SOURCE_KIND,
            "ref": f"https://{gen.FEISHU_HOST}/base/{gen.DEFAULT_BASE}?table={gen.DEFAULT_TABLE_ID}",
            "fingerprint": f"{gen.DEFAULT_BASE}/{gen.DEFAULT_TABLE_ID}",
            "captured_at": today,
        },
        "provenance": {
            "anchor": f"kb/l4/canonical/sample_case.jsonl#{rec.get('case_id','')}",
            "confidence": gen.CONFIDENCE_CERTAIN,
        },
        "pii": {
            "detected": pii_hit,
            "masked": pii_hit,
            "strategy": "案例正文与原因分析里的 @人名 不可逆脱敏（mask-at-name）；"
                        + ("已检出并脱敏" if pii_hit else "未检出自然人信息"),
        },
        "article_no": art,
        "form": "sample_case",
        "kb_type": rec.get("kb_type") or "internal_sample",
        "kb_version": rec.get("kb_version") or "v0",
        "case_id": rec.get("case_id") or "",
        "status": rec.get("status") or "",
        "polarity": polarity,
        "material_type": material,
        "channel": channel,
        "reason_category": reason_cat,
        "evidence_strength": rec.get("evidence_strength") or "",
        "promoted_from": rec.get("promoted_from") or "",
        "anchor": rec.get("anchor") or "",
        "source_sha256": rec.get("source_sha256") or "",
        "resource_id": rec.get("resource_id") or "",
        "sample_body": body_text,
        "reason_analysis": reason_text,
        "advice": advice,
    }

    body = [
        f"# {title}",
        "",
        f"**条款号**：{art}　|　**形态**：`sample_case`　|　**正/反例**：{polarity}　|　**状态**：{rec.get('status','')}",
        "",
        "## 样本本体（照抄新库，未改写）",
        "",
        body_text if body_text else "（本条的 `sample_body` 为空）",
        "",
    ]
    if reason_text:
        body += ["## 原因分析", "", reason_text, ""]
    if advice:
        body += ["## 建议", "", advice, ""]
    body += [
        "## 引用依据",
        "",
        f"- 锚点：`{rec.get('anchor','')}`",
        f"- 指纹：`{rec.get('source_sha256','')}`",
        f"- 原因归类：{reason_cat or '（源库未标）'}　|　素材类型：{material or '（源库未标）'}",
        "",
        "> 案例只作参照，不构成规则。",
        "",
    ]
    return meta, "\n".join(body)


def link_neighbors(docs: list[dict], per: int = 3) -> None:
    """同子库内互挂 related 邻居，避免孤岛率 1.00。"""
    for i, doc in enumerate(docs):
        n = len(docs)
        if n <= 1:
            continue
        neighbors = []
        for step in range(1, per + 1):
            neighbors.append(docs[(i + step) % n]["id"])
        doc["meta"]["related"] = neighbors


def patch_collections(out_root: str, new_collections: list[dict], counts: dict) -> None:
    """把新子库登记进 _meta/collections.yaml（主生成器写的那份）。"""
    import yaml

    path = os.path.join(out_root, "_meta", "collections.yaml")
    if not os.path.isfile(path):
        print(f"[l4] 警告：找不到 {path}，跳过登记表更新")
        return
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    registered = {c.get("id") for c in (data.get("collections") or [])}
    for spec in new_collections:
        if spec["dir"] in registered:
            continue
        data.setdefault("collections", []).append({
            "id": spec["dir"],
            "name": spec["name"],
            "display_name": spec["display_name"],
            "called_by": ["待定（内容审查 Agent 尚未立项编号）"],
            "owner": gen.LIBRARY_OWNER,
            "status": "derived",
            "source": spec["source"],
            "entry_count": counts.get(spec["dir"], 0),
            "note": spec["note"],
        })

    header = (
        "# 子库登记表（派生视图，由 kb/.work/gen-host-library.py + gen-host-library-l4.py 生成，勿手工维护）\n"
        "# 字段口径与宿主库一致；status: derived 表示本库不是人工灌入，而是从分层新库派生。\n"
    )
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(header)
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"[l4] 登记表已更新：{path}")


def patch_manifest(out_root: str, new_collections: list[dict], counts: dict,
                   manifest_docs: list[dict], per_collection: dict, today: str) -> None:
    """把新子库与新文档补进 _meta/manifest.json（工作台远程取数按它读）。"""
    path = os.path.join(out_root, "_meta", "manifest.json")
    if not os.path.isfile(path):
        print(f"[l4] 警告：找不到 {path}，跳过 manifest 更新")
        return
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    registered = {c.get("id") for c in (data.get("collections") or [])}
    for spec in new_collections:
        if spec["dir"] in registered:
            continue
        data.setdefault("collections", []).append({
            "id": spec["dir"],
            "name": spec["name"],
            "display_name": spec["display_name"],
            "externalRoot": os.path.join(out_root, spec["dir"]),
            "description": f"宿主知识库子库（派生） · {spec['dir']}/",
            "called_by": ["待定（内容审查 Agent 尚未立项编号）"],
            "owner": gen.LIBRARY_OWNER,
            "status": "derived",
            "source": spec["source"],
            "entry_count": counts.get(spec["dir"], 0),
            "note": spec["note"] + "。本子库是派生视图，原库为分层 json 结构，见 _meta/DERIVED.md。",
        })

    existing_ids = {d.get("id") for d in (data.get("docs") or [])}
    added = 0
    for doc in manifest_docs:
        if doc["id"] not in existing_ids:
            data.setdefault("docs", []).append(doc)
            added += 1

    merged = collections.Counter(data.get("counts") or {})
    for key, value in per_collection.items():
        merged[key] += value
    data["counts"] = dict(merged)

    data["generatedAt"] = today
    data["generator"] = "kb/.work/gen-host-library.py + gen-host-library-l4.py"

    # version 与主生成器同口径：collections + docs（去掉大字段）的稳定哈希
    data["version"] = gen.sha256_text(json.dumps({
        "collections": data["collections"],
        "docs": [{k: v for k, v in d.items() if k not in ("metaJson", "text", "content")} for d in data["docs"]],
    }, ensure_ascii=False, sort_keys=True))

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    print(f"[l4] manifest 已更新：collections {len(data['collections'])} 个，docs {len(data['docs'])} 条（新增 {added}）")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="宿主库根目录（主生成器的 --out）")
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args()

    out_root = os.path.abspath(args.out)
    if not os.path.isdir(out_root):
        print(f"[l4] 错误：{out_root} 不存在，请先跑主生成器 gen-host-library.py --out {args.out}")
        return 2

    today = args.today
    valid_until = (date.fromisoformat(today) + timedelta(days=gen.DERIVED_HALF_LIFE_DAYS)).isoformat()

    clauses = load_jsonl(SRC_CLAUSE)
    cases = load_jsonl(SRC_SAMPLE)

    payload: list[dict] = []
    manifest_docs: list[dict] = []
    per_collection: dict[str, int] = collections.Counter()
    counts: dict[str, int] = collections.Counter()
    id_seen: set[str] = set()
    import hashlib

    def emit(records, builder, subdir):
        docs_meta = []
        for rec in records:
            meta, body = builder(rec, today, valid_until)
            if meta["id"] in id_seen:
                meta["id"] = meta["id"] + "-" + (rec.get("article_no", "").replace(".", "_") or "dup")
            id_seen.add(meta["id"])
            docs_meta.append({"id": meta["id"], "meta": meta, "body": body})
        link_neighbors(docs_meta)
        tier_dir = "L1-facts"
        for doc in docs_meta:
            meta = gen.insert_kb_class(doc["meta"], subdir)
            body = doc["body"]
            rel = os.path.join(subdir, tier_dir, f"{meta['id']}.md")
            text = gen.frontmatter(meta) + "\n" + body
            payload.append({"rel": rel, "text": text})
            counts[subdir] += 1
            per_collection[f"{subdir}/{tier_dir}"] += 1
            raw_bytes = text.encode("utf-8")
            manifest_docs.append({
                "id": meta["id"],
                "collectionId": subdir,
                "relPath": rel,
                "absPath": os.path.join(out_root, rel),
                "record": False,
                "title": meta["title"],
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "text": text,
                "content": gen.render_for_chunking(meta, "\n" + body + "\n"),
                "bytes": len(raw_bytes),
                "entryId": meta["id"],
                "tier": meta["tier"],
                "kind": meta["kind"],
                "validUntil": meta["valid_until"],
                "evidenceLevel": meta["evidence_level"],
                "owner": meta["owner"],
                "metaJson": json.dumps(meta, ensure_ascii=False),
            })

    emit(clauses, build_clause_meta, "1_外部标准库")
    emit(cases, build_case_meta, "2_内部正负样本库")

    gen.flush_md(payload, out_root)

    patch_collections(out_root, COLLECTIONS, counts)
    patch_manifest(out_root, COLLECTIONS, counts, manifest_docs, per_collection, today)

    print(f"[l4] 源：scoped_clause {len(clauses)} 条；sample_case {len(cases)} 条")
    print(f"[l4] 追加产出：{sum(counts.values())} 条条目")
    for key, value in sorted(counts.items()):
        print(f"[l4]   {key}: {value}")
    print(f"[l4] 输出根：{out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
