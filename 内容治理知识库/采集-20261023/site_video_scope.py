#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""官网视频的**取舍口径** —— 只有一个实现，谁用谁 import。

## 为什么单独抽出来

2026-10-23 现场踩到：`build_collect_rows.py`（写入器）与 `fix_cells.py`（修正器）
**各写了一份口径**，结果写入器把修正器刚清空的 3 格又填了回去 —— 两把尺子打架，
同一件事两个实现，必然互相推翻。所以口径放这里，两边都调它。

## 口径是什么

**官网「单视频」只认「仅在该产品页面出现」的视频。**

依据（2026-10-23 实测，不是推测）：

- S12 Pro+吸奶器 / BW-NDT洗涤剂片 / BS03洗涤块 三页各有一个
  `Featured product video` 版块，里面是**同一批 12 个视频**（上传档位编号连号
  `81749620`–`81749631`）；
- 这三页的版块**实例与模板 id 并不相同**
  （`template--20507183055046__lt_firework_section_Kt6mGqtworow` vs
   `template--20507181416646__lt_firework_section_eXRrRe`）⇒ **不是模板继承出来的，
  是各页各自配了同一批素材**；
- **首页 0 个视频** ⇒ 也不是站级品牌视频；
- 三页对应的产品互不相关（吸奶器 / 洗涤剂片 / 洗涤块）。

⇒ 结论：**无法把这 12 个视频归给其中任何一个产品**。既然归不了，就不写进任何产品的格子里 ——
「查不到就空着，不编」比「填一个看着像的」安全。要填必须先有人看过内容再说。

⚠️ **未能判定的一点（摆出来，不藏）**：这批视频**拍的是什么，我不知道** ——
当前模型（deepseek-v4.1-flash）**没有图像输入**，我读不了封面缩略图，也看不了视频。
判「不属于这三个产品」的依据是**配置结构**（跨页共享、非模板、非站级），不是**画面内容**。
反过来的可能没有被排除：它也可能是其中某个产品的视频，被**误配**到了另外两页上
—— 那本身就是一条内容治理问题，但**得有人看一眼封面**才能定。
"""


def site_video_scope(site_records):
    """返回 {产品中文名: [仅本页独有的视频URL]}。

    跨页共享的视频（出现在 >1 个产品页）**一律剔除** —— 见模块头部依据。
    """
    seen = {}
    for r in site_records:
        if not r.get("ok"):
            continue
        for u in set(r.get("视频") or []):
            seen[u] = seen.get(u, 0) + 1
    out = {}
    for r in site_records:
        if not r.get("ok"):
            continue
        out[r["产品中文名"]] = [u for u in (r.get("视频") or []) if seen.get(u, 0) == 1]
    return out


def site_shared_videos(site_records):
    """返回被多个产品页共享的视频 —— 用于报告里点名「这些没能归属」。"""
    seen = {}
    for r in site_records:
        if not r.get("ok"):
            continue
        for u in set(r.get("视频") or []):
            seen.setdefault(u, []).append(r["产品中文名"])
    return {u: names for u, names in seen.items() if len(names) > 1}