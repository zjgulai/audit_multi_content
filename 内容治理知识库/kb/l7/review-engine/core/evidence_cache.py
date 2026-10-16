#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_cache.py —— 依据 findings 的「run 内缓存」：格式与校验的**唯一真源**。

## 为什么单独成一个文件（2026-10-01）

同一份缓存的**写方有两个**：

  ① `kb-content-review/scripts/review.py` —— 依据侧跑完，顺手把依据落成中间产物；
  ② `l7/review-engine/core/with_kb_evidence.py` —— 适配器现跑之后也允许落缓存。

**读方**是适配器（`--findings-from`）。格式只要各写一份，迟早漂移；
而漂移的后果不是"读不到"，是**读错**：把 A 文案的依据算到 B 文案上 ——
结论看着有据可查，实际张冠李戴。所以 schema 常量与三道校验只在这里定义一次。

## 三道校验（缺一不可）

  ① `schema` 必须等于 `CACHE_SCHEMA`；
  ② `text_sha256` 必须等于**本次**文本的 sha256；
  ③ `payload` 必须是对象。

任一不过 → 返回错误，调用方**宁可重跑也不复用可疑依据**。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_SCHEMA = "kb-evidence-findings-cache/1"


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def envelope(text: str, payload: dict, source: str = "") -> dict:
    """把一个依据 payload 包成可落盘的缓存对象。"""
    return {
        "schema": CACHE_SCHEMA,
        "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "text_sha256": text_sha256(text),
        "source": source,
        "payload": {k: v for k, v in (payload or {}).items() if not k.startswith("_")},
    }


def write_cache(path, text: str, payload: dict, source: str = "") -> str:
    """落缓存；返回写入路径。写不进去应抛 OSError，由调用方决定是否降级。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(envelope(text, payload, source), ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return str(p)


def read_cache(path, text: str, mark: bool = True):
    """读缓存，返回 `(payload, None)` 或 `(None, 错误说明)`。"""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        return None, "findings 缓存读不到：%s（%s）" % (path, e)
    except json.JSONDecodeError as e:
        return None, "findings 缓存不是合法 JSON：%s（%s）" % (path, e)
    if obj.get("schema") != CACHE_SCHEMA:
        return None, "findings 缓存 schema 不符：期望 %s，实际 %r" % (CACHE_SCHEMA, obj.get("schema"))
    want, got = text_sha256(text), obj.get("text_sha256")
    if got != want:
        return None, ("findings 缓存与本次文本不符（缓存 %s… ／ 本次 %s…）—— 拒绝复用，"
                      "否则会把另一条文案的依据算到这条上" % (str(got)[:12], want[:12]))
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return None, "findings 缓存里没有 payload 对象"
    if mark:
        payload = dict(payload)
        payload["_findings_source"] = {"mode": "cache", "path": str(path),
                                       "cached_at": obj.get("cached_at")}
    return payload, None
