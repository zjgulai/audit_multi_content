#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""csv_to_json.py —— 把 CSV 按行转成 JSON（对账小工具，只用标准库）。

## 用法

    python3 tools/csv_to_json.py 对账.csv                  # 打印到屏幕
    python3 tools/csv_to_json.py 对账.csv -o 对账.json       # 写文件
    python3 tools/csv_to_json.py a.csv b.csv               # 各自生成 a.json / b.json
    python3 tools/csv_to_json.py 对账.csv --jsonl           # 每行一个 JSON，便于 diff / 灌库
    python3 tools/csv_to_json.py 对账.csv --indent 0        # 压成单行
    python3 tools/csv_to_json.py 对账.csv --encoding gbk    # 中文乱码时手动指定

退出码：0 全部成功 / 1 有文件失败 / 2 参数错

## 对账相关的取舍

- **表头当键**，一行一个对象。缺的列补 `null`，多出来的列进 `_extra` —— 不静默丢，
  否则对账会假平。空单元格保持 `""`，不转 `null`：一个是「有列没值」，一个是「没这列」。
- 默认 `indent=2` + `ensure_ascii=False`，图的是能被 git diff 和肉眼比对。
- 编码自动探测：UTF-8(BOM) → UTF-8 → GBK，Excel 导出的中文 CSV 基本都能吃。
- 本脚本写 `.json` 是安全的；若 `-o` 落到 `.txt`/`.md`，本机有信封态问题，
  写完跑一下 `python3 tools/envelope_gate.py <文件>` 验一遍。
"""
from __future__ import annotations

import argparse
import codecs
import csv
import json
import sys
from pathlib import Path

ENCODINGS = ("utf-8-sig", "utf-8", "gbk")


def sniff_encoding(path: Path, forced: str) -> str:
    """返回能解开这个文件的编码；forced 非空就直接用。"""
    if forced:
        return forced
    raw = path.read_bytes()
    # utf-8-sig 解无 BOM 的文件也不报错，所以 BOM 得自己认，别乱报编码
    candidates = ENCODINGS if raw[:3] == codecs.BOM_UTF8 else ENCODINGS[1:]
    for enc in candidates:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError("试过 %s 都解不开，请用 --encoding 指定" % (ENCODINGS,))


def convert(path: Path, forced: str) -> tuple:
    """读一个 CSV，返回（行列表, 实际用的编码）。"""
    enc = sniff_encoding(path, forced)
    with path.open("r", encoding=enc, newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("没有表头：CSV 第一行必须是列名")
        rows = []
        for row in reader:
            # 按表头顺序取；行比表头短 -> 缺的列 get 出 None，落成 null（不整列丢）
            clean = {key: row.get(key) for key in reader.fieldnames}
            if None in row:  # 行比表头长的部分，DictReader 挂在 None 键上
                clean["_extra"] = row[None]
            rows.append(clean)
    return rows, enc


def write_out(rows: list, target: Path, jsonl: bool, indent: int) -> None:
    """写文件或写屏幕。target 为 None 时写屏幕。"""
    if jsonl:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    else:
        text = json.dumps(rows, ensure_ascii=False, indent=indent or None) + "\n"
    if target is None:
        sys.stdout.write(text)
    else:
        target.write_text(text, encoding="utf-8")


def main(argv: list = None) -> int:
    ap = argparse.ArgumentParser(description="把 CSV 按行转成 JSON（对账小工具）")
    ap.add_argument("inputs", nargs="+", type=Path, help="一个或多个 .csv")
    ap.add_argument("-o", "--out", type=Path, help="输出文件；只配一个输入，默认打印到屏幕")
    ap.add_argument("--jsonl", action="store_true", help="每行一个 JSON 对象，便于 diff 和灌库")
    ap.add_argument("--indent", type=int, default=2, help="缩进空格数，0 = 压成单行（默认 2）")
    ap.add_argument("--encoding", choices=ENCODINGS, default="", help="手动指定编码，默认自动探测")
    ap.add_argument("--quiet", action="store_true", help="不打印每行的统计")
    args = ap.parse_args(argv)

    if args.out and len(args.inputs) > 1:
        print("✗ --out 只能配一个输入；多个输入时默认各自生成同名 .json", file=sys.stderr)
        return 2

    failed = 0
    for path in args.inputs:
        try:
            rows, enc = convert(path, args.encoding)
        except (OSError, ValueError, UnicodeDecodeError, csv.Error) as exc:
            print("✗ %s：%s" % (path, exc), file=sys.stderr)
            failed += 1
            continue

        if args.out:
            target = args.out
        elif len(args.inputs) == 1:
            target = None  # 单个输入又没给 -o -> 打印到屏幕
        else:
            target = path.with_suffix(".json")

        try:
            write_out(rows, target, args.jsonl, args.indent)
        except OSError as exc:
            print("✗ %s：写不进去 -> %s" % (path, exc), file=sys.stderr)
            failed += 1
            continue

        if not args.quiet:
            print("✓ %s -> %s  %d 行 / %d 列  (%s)"
                  % (path, target or "<屏幕>", len(rows),
                     len(rows[0]) if rows else 0, enc), file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
