#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stamp_meta.py —— 落章的**编排归属**字段（批次21 · 第1块）。

## 它解决什么（D1 的结构性根因）

`kb/l7/scripts/skill_invocation_audit.py` 的**落章契约**（该文件 `:56-61` 原文）早就写着：

    kb/<layer>/runs/<RUN>*.json 里至少一条记录满足：
      · `run_id` 以 `<RUN>` 开头，**或 `pipeline_run_id == <RUN>`**；
      · 带 skill / skill_id / skills 任一字段

**`stamp_of()` 也早就实现了读这一半**（`:186` `pipe = str(r.get("pipeline_run_id") or "")`）。
但**全库没有任何写入者**（实测 `l0..l6/runs/` 0 命中）⇒ 那一支**永远是空**。

⇒ 后果：编排器跑一次 `--via-skill`（RUN=A），各层引擎各自用自己的 RUN（B/C/D…）写落章，
   落章里 `run_id=B ≠ A`、又没有 `pipeline_run_id` ⇒ **审计在 A 名下查不到任何落章** ⇒
   **E2 恒红**（且层数越多红越多）。

⇒ 修法**不是改判据**（那才是放松），而是**把编排器的 RUN 号透传下去、让落章写上 `pipeline_run_id`** ——
   **用契约自带的字段**。

## 怎么透传：环境变量（不改各引擎的 argv 契约）

`KB_PIPELINE_RUN_ID` 由编排器 `kb_pipeline.py` 在执行每层引擎时注入；
本模块只在**写落章前**把它读出来放进记录。

★ 为什么用环境变量而不是加 `--pipeline-run` 参数：
  各层引擎的 argv 已经承载 `RUN` / `--apply` / `--skill` 等，**再动 argv 解析风险大**；
  环境变量**不占位置参数**、默认缺失即行为不变。

## 契约

`stamp_fields()` 恒返回 `{"pipeline_run_id": <str|None>}`：
  · 有 `KB_PIPELINE_RUN_ID` ⇒ 写该值（**这才是 E2 要的**）；
  · 没有 ⇒ 写 `None` —— **仍然写这个键**，
    这样「这一跑不是编排器起的」在落章里**看得见**，而不是靠「键不存在」去猜。
"""
from __future__ import annotations

import os

#: 编排器注入的环境变量名
ENV_KEY = "KB_PIPELINE_RUN_ID"


def pipeline_run_id():
    """本跑所属的编排 RUN（没有则 None）。"""
    v = (os.environ.get(ENV_KEY) or "").strip()
    return v or None


def stamp_fields():
    """合并进落章字典的字段。"""
    return {"pipeline_run_id": pipeline_run_id()}
