#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_preflight.py — L3 蒸馏跑批前的只读预检（不做任何写操作）。

检查三件事：
  1. 归档（红线①）：kb/l3/rejected.jsonl 是否存在、行数、sha256；
     给了 --run 时，校验 kb/l3/_archive/rejected-pre-<RUN>.jsonl 存在且 sha256 与源一致。
  2. 只追加基线（A3）：打印 kb/l3/candidates/*.jsonl 的逐文件行数与 sha256 清单，
     供跑批后逐字节比对（本脚本只打印，不落盘）。
  3. 台账口径提醒：打印台账分母提示（分母是 L2 单元数，不是条款数）。

退出码：0=全部预检通过；2=预检不通过（含缺归档）；1=用法/输入错误。

用法：
  python3 l3_preflight.py --kb-root ~/.dsh/Momcozy知识库 --run 20260930-1800
  python3 l3_preflight.py --kb-root ~/.dsh/Momcozy知识库 --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

CANDIDATES = ("rules.jsonl", "sample_cases.jsonl", "scoped_clauses.jsonl")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    n = 0
    with path.open("rb") as fh:
        for _ in fh:
            n += 1
    return n


def file_facts(path: Path) -> dict:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    return {"path": str(path), "exists": True,
            "lines": count_lines(path), "sha256": sha256(path)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="l3_preflight.py",
        description="L3 蒸馏跑批前的只读预检（归档 / 只追加基线 / 台账口径）。不写任何文件。")
    ap.add_argument("--kb-root", required=True,
                    help="知识库根目录（kb/ 的上一级），例如 ~/.dsh/Momcozy知识库")
    ap.add_argument("--run", default=None,
                    help="本次 RUN 标记（YYYYMMDD-HHMM）；给了就校验归档存在且指纹一致")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（便于接流水线）")
    args = ap.parse_args(argv)

    root = Path(args.kb_root).expanduser()
    if not root.is_dir():
        print(f"[error] --kb-root 不是目录: {root}", file=sys.stderr)
        return 1
    l3 = root / "kb" / "l3"
    if not l3.is_dir():
        print(f"[error] 找不到 L3 目录: {l3}（--kb-root 应为 kb/ 的上一级）", file=sys.stderr)
        return 1

    if args.run is not None and not args.run.strip():
        print("[error] --run 不能是空串", file=sys.stderr)
        return 1

    report = {"kb_root": str(root), "checks": [], "ok": True}

    def add(name, ok, detail):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["ok"] = False

    ledger = l3 / "rejected.jsonl"
    led = file_facts(ledger)
    add("台账存在", led["exists"], led)

    arch = None
    if args.run:
        arch = file_facts(l3 / "_archive" / f"rejected-pre-{args.run}.jsonl")
        add("归档存在（红线①）", arch["exists"], arch)
        if arch["exists"] and led["exists"]:
            add("归档指纹与源一致（A2）", arch["sha256"] == led["sha256"],
                {"archive_sha256": arch["sha256"], "ledger_sha256": led["sha256"]})
    else:
        add("归档校验", False, "未给 --run：无法校验归档是否为当次基线（红线①要求跑前归档并校验 sha256）")

    base = {}
    for name in CANDIDATES:
        base[name] = file_facts(l3 / "candidates" / name)
    report["append_only_baseline"] = base
    add("候选基线可取（A3）", any(v.get("exists") for v in base.values()),
        "跑批后必须逐字节比对：旧行未变 + 新行只在末尾追加")

    units = root / "kb" / "l2" / "units.jsonl"
    report["ledger_denominator"] = file_facts(units)
    add("台账分母可取（L2 单元）", report["ledger_denominator"]["exists"],
        "台账行数受上游切分粒度影响，不是质量指标；分母是 L2 单元数")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"== L3 跑前预检：{root} ==")
        for c in report["checks"]:
            print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}")
            print(f"         {json.dumps(c['detail'], ensure_ascii=False)}")
        print("\n-- 只追加基线（跑批后逐字节比对，脚本不落盘）--")
        for k, v in base.items():
            print(f"  {k}: " + (f"{v['lines']} 行 sha256={v['sha256'][:16]}…" if v["exists"] else "缺失"))
        print("\n结论：" + ("预检通过，可以跑批（仍须先归档）" if report["ok"]
                          else "预检不通过 —— 先补归档/修正 kb-root，别跑 l3_distill_run.py"))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
