#!/usr/bin/env python3
"""
把飞书表格「W1卖点匹配证据库_检索阅读版_0827更新」抓成本地缓存，供生成器读取。

为什么单独一步、不并进 publish.sh：
    这一步**需要飞书的有效授权**（sheets:spreadsheet:read），而授权是按用户的、会过期；
    publish.sh 则是纯本地、可无人值守跑。把两者分开，发布链路就不会因为授权过期而挂掉。
    抓取失败/过期时，生成器继续用上一次的缓存，并在条目里保留当时的抓取时间与指纹。

为什么用 local cache 而不是直接写进 l2 单元层：
    权威分层库（kb/l0…l7）有自己的入库闸门与晋升链，手工往里塞数据会破坏那套纪律。
    所以抓来的东西落在**派生区**（kb/.work/sources/），条目里用 `provenance.anchor`
    精确指到「哪个工作表、哪一行」，再用 `source.fingerprint` 锁住抓取时的那份数据。

用法：
    python3 kb/.work/fetch-w1-evidence.py            # 抓取并覆盖缓存
    python3 kb/.work/fetch-w1-evidence.py --check     # 只看现在缓存里有什么，不联网
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import csv
import io
from datetime import datetime

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(KB, ".work", "sources")
OUT = os.path.join(SOURCES, "w1-evidence.json")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")

# 表格 token：wiki 节点 token 与 obj_token 都能读（实测两者等价）
SPREADSHEET_TOKEN = "ZBAtsIiFSh3TbUt4CNvcoWPgnLe"
WIKI_NODE = "EsCdw2A7tiz67Rk8LgMce2TAnEh"
SHEET_URL = f"https://momcozy-in.feishu.cn/wiki/{WIKI_NODE}"

SHEETS = [
    ("0XppQz", "00_使用说明"),
    ("1huvaX", "01_卖点护照"),
    ("2preBH", "02_表达边界"),
    ("3rvAjF", "03_文献研究证据库"),
    ("4PRZro", "04_内容转译卡"),
    ("5Iotao", "05_验证缺口"),
    ("6eXrIM", "06_术语与口径"),
]


def fetch_sheet(sheet_id: str) -> dict:
    """抓一个工作表；用 annotated_csv（带 [row=N] 行号前缀），按官方 warning 的读法解析。

    为什么不自己数行号：官方返回里的 warning_message 明确写着「必须直接读取每行开头的
    [row=N] 前缀，不要自己数行、也不要用 ID 列的值推导」——这些表的行号会跳号。
    条目里的 anchor 要指到具体行，所以行号必须是真的。
    """
    proc = subprocess.run(
        [LARK, "sheets", "+csv-get",
         "--spreadsheet-token", SPREADSHEET_TOKEN,
         "--sheet-id", sheet_id,
         "--range", "A1:T200",
         "--as", "user", "--json"],
        capture_output=True, text=True, timeout=90,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"lark-cli 退出码 {proc.returncode}：{proc.stderr[:200]}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok"):
        raise RuntimeError(f"抓取失败：{json.dumps(payload.get('error'), ensure_ascii=False)[:200]}")
    data = payload.get("data") or {}
    annotated = data.get("annotated_csv") or ""

    rows: list[dict] = []
    for line in annotated.splitlines():
        m = re.match(r"^\[row=(\d+)\] ?(.*)$", line)
        if not m:
            continue
        row_no = int(m.group(1))
        cells = next(csv.reader(io.StringIO(m.group(2))))
        if not any(c.strip() for c in cells):
            continue
        rows.append({"row": row_no, "cells": [c.strip() for c in cells]})
    return {
        "sheet_id": sheet_id,
        "region": data.get("current_region") or "",
        "revision": data.get("revision"),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只看缓存，不联网")
    args = parser.parse_args()

    if args.check:
        if not os.path.isfile(OUT):
            print(f"缓存不存在：{OUT}")
            return 1
        cached = json.load(open(OUT, encoding="utf-8"))
        print(f"缓存：{OUT}")
        print(f"  抓取时间：{cached.get('fetched_at')}")
        print(f"  指纹    ：{cached.get('fingerprint')}")
        for name, sheet in (cached.get("sheets") or {}).items():
            print(f"  {name:22} {sheet.get('region'):12} {len(sheet.get('rows') or [])} 行  revision={sheet.get('revision')}")
        return 0

    os.makedirs(SOURCES, exist_ok=True)
    result = {
        "source": "feishu-sheet",
        "url": SHEET_URL,
        "spreadsheet_token": SPREADSHEET_TOKEN,
        "title": "W1卖点匹配证据库_检索阅读版_0827更新",
        "fetched_at": datetime.now().strftime("%Y-%m-%d"),
        "sheets": {},
    }
    for sheet_id, name in SHEETS:
        sheet = fetch_sheet(sheet_id)
        result["sheets"][name] = sheet
        print(f"  {name:22} {sheet['region']:12} {len(sheet['rows'])} 行  revision={sheet['revision']}")

    body = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=1)
    result["fingerprint"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=1)
    total = sum(len(s["rows"]) for s in result["sheets"].values())
    print(f"\n已写入 {OUT}")
    print(f"  指纹：{result['fingerprint'][:16]}…（{total} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
