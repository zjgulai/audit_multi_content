#!/usr/bin/env python3
"""ingest.py - root-skills-check 蒸馏入库助手

把一条高质量结果写进 assets/knowledge-base/：算指纹、去重、更新 index.yaml、输出 delta。
只负责「自动成长」（本 skill 唯一新写的能力），不重写 eval 闸门脚本。

用法:
    python scripts/ingest.py --type defect|golden|restoration|link \
        --title "标题" --content-file content.md --source-report report.yaml \
        [--source-skill "被测skill名"]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

KB = Path(__file__).resolve().parent.parent / "assets" / "knowledge-base"
INDEX = KB / "index.yaml"

TYPES = {
    "defect": "defects",
    "golden": "goldens",
    "restoration": "restorations",
    "link": "links",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_index() -> dict:
    if yaml is None:
        raise SystemExit("[error] 未安装 PyYAML，请先 pip install pyyaml")
    if not INDEX.exists():
        return {"version": "1.0.0", "updated_at": "", "stats": {
            "defects": 0, "goldens": 0, "restorations": 0, "links": 0}, "entries": []}
    data = yaml.safe_load(INDEX.read_text(encoding="utf-8")) or {}
    kb = data.get("knowledge_base") or {}
    kb.setdefault("version", "1.0.0")
    kb.setdefault("updated_at", "")
    kb.setdefault("stats", {"defects": 0, "goldens": 0, "restorations": 0, "links": 0})
    kb.setdefault("entries", [])
    return kb


def _save_index(kb: dict) -> None:
    INDEX.write_text(
        yaml.safe_dump({"knowledge_base": kb}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _source_fingerprint(source_report: str) -> str:
    p = Path(source_report)
    if p.exists():
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return hashlib.sha256(source_report.encode("utf-8")).hexdigest()[:16]


def _export_top_defects(n: int) -> None:
    """只读导出知识库 Top-N 缺陷，供 doctor/eval 批量预检消费。

    存储/蒸馏仍由本 skill（root-skills-check）独占；此出口只输出缺陷标题与要点，
    不复制规则正文到其他成员。N<=0 表示全部。
    """
    kb = _load_index()
    defects = [e for e in kb.get("entries", []) if e.get("type") == "defect"]
    if n > 0:
        defects = defects[:n]
    out = []
    for e in defects:
        f = KB / (e.get("file") or "")
        head = ""
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "---", "type:", "title:", "source_", "fingerprint:", "ingested_at:")):
                    head = s[:200]
                    break
        out.append({
            "title": e.get("title"),
            "source_skill": e.get("source_skill"),
            "file": e.get("file"),
            "pattern": head,
        })
    print(yaml.safe_dump({"top_defects": out}, allow_unicode=True, sort_keys=False), end="")


def main() -> int:
    ap = argparse.ArgumentParser(description="root-skills-check 蒸馏入库助手（入库 + 只读导出）")
    ap.add_argument("--type", required=False, choices=sorted(TYPES), help="入库类型（用 --export-top-defects 时无需提供）")
    ap.add_argument("--title", required=False)
    ap.add_argument("--content-file", required=False, help="条目正文 markdown（模式/金标/对照片段，不搬整份 HTML）")
    ap.add_argument("--source-report", required=False, help="来源报告路径（算来源指纹）")
    ap.add_argument("--source-skill", default="", help="被测 skill 名")
    ap.add_argument("--export-top-defects", type=int, default=0, metavar="N",
                    help="只读导出知识库 Top-N 缺陷（供 root-skills-doctor/eval 批量预检消费）；N<=0 导出全部，与入库参数互斥")
    args = ap.parse_args()

    if args.export_top_defects:
        if yaml is None:
            raise SystemExit("[error] 未安装 PyYAML，请先 pip install pyyaml")
        _export_top_defects(args.export_top_defects)
        return 0
    if not args.type or not args.title or not args.content_file or not args.source_report:
        ap.error("入库需要 --type/--title/--content-file/--source-report；只读导出请用 --export-top-defects N")

    content = Path(args.content_file).read_text(encoding="utf-8")
    src_fp = _source_fingerprint(args.source_report)
    fp = hashlib.sha256(f"{src_fp}:{args.type}:{content}".encode("utf-8")).hexdigest()[:16]

    kb = _load_index()
    for e in kb.get("entries", []):
        if e.get("fingerprint") == fp:
            print(f"[skip] 指纹 {fp[:8]} 已存在，跳过（重复）")
            print("数据资产 delta: 新增 0 条 / 跳过 1 条重复")
            return 0

    subdir = TYPES[args.type]
    out_dir = KB / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{args.type}-{fp[:8]}.md"
    out_path = out_dir / fname
    now = _now()
    header = (
        "---\n"
        f"type: {args.type}\n"
        f"title: {args.title}\n"
        f"source_skill: {args.source_skill}\n"
        f"source_report: {src_fp}\n"
        f"fingerprint: {fp}\n"
        f"ingested_at: {now}\n"
        "---\n\n"
    )
    out_path.write_text(header + content, encoding="utf-8")

    entry = {
        "type": args.type,
        "title": args.title,
        "source_skill": args.source_skill,
        "source_report": src_fp,
        "fingerprint": fp,
        "ingested_at": now,
        "file": f"{subdir}/{fname}",
    }
    entries = kb.get("entries") or []
    entries.insert(0, entry)
    kb["entries"] = entries
    kb["stats"][TYPES[args.type]] = kb.get("stats", {}).get(TYPES[args.type], 0) + 1
    kb["updated_at"] = now
    _save_index(kb)

    print(f"[ok] 已入库 {args.type}: {args.title} → {subdir}/{fname}")
    print(f"数据资产 delta: 新增 1 条（{args.type}: {args.title}）/ 跳过 0 条重复")
    return 0


if __name__ == "__main__":
    sys.exit(main())
