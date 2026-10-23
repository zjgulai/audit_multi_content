#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总装「产品 × 内容形态 × 平台」测试矩阵 135 行（9 产品 × 5 枚举 × 3 平台）。

目标：base `RY2UbCRjXaeeWwscUPScVN5AnQc`（wiki `Lntdw8XqmifewjkdEckcXYH8nOV`）
      / table `tblTPsjiyOHYfUc0`（「守衡测试」）
数据源：同 Base 的 `tblsR4t1pXSD6m7y`（「商品维表」，441 行）—— 取 `产品spu` / `产品英文名`。

## 口径

1. **产品清单是任务给定的**（Owner 2026-10-23），按品线列出 **9** 个具体产品
   （Owner 当天先给 15 个、随即收窄为「每个品线只采集 3 个」⇒ 以 SPEC 为准）。
   `产品中文名` 逐字取「商品维表」的值，**不由我改写、不由我补全**。
2. **SPU 与英文名一律从商品维表取，禁止手抄** —— 脚本按 `产品中文名` **精确匹配**
   （去空格 / 全角空格 / 大小写），**命中数必须恰好 = 1**，否则整批不产出。
   手抄 15 条英文名会引入看不出来的转录错（本项目栽过这个）。
3. **`产品线` 用库内受控词表**：吸奶器 / 清洗机 / 婴儿监控器。
   ⚠️ 注意与商品维表的 `产品品线` **不是同一套值**（那边是 `清洗机 PDT` / `BBM PDT`）。
   这里跟**守衡测试表的既有写法**（短名），不跟商品维表。
4. **`内容类型` 本轮改用 5 个新枚举**：单图 / 多图 / 单视频 / 文本 / 链接。
   ⚠️ 这是**对 2026-10-22 口径的变更** —— 那天 `采集-20261022/build_rows.py` 写的是
   「`内容类型` 用库内既有值（文案 / 视频），**不自创任何一个枚举值**」。
   变更依据 = Owner 2026-10-23 的任务原话（「每个具体产品下拆解枚举值（单图/多图（两张图）/
   单视频/文本/链接）」）。**原话里的「（两张图）」我按枚举名落成 `多图`**，定义记在
   本文件与交付件里，没有丢；要改成逐字带括号，改 ENUMS 一行即可。
5. 本矩阵**只填产品识别列 + 内容类型**；`采集数据` / `渠道` 留空（素材还没采）。
   **人/引擎的列一个都不碰**（问题等级 / 问题描述 / 证据+来源 / Codex* / 问题编号）。

用法：python3 build_prod_matrix.py
"""
import json
import sys

sys.path.insert(0, "../../tools")
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
SRC_TABLE = "tblsR4t1pXSD6m7y"      # 商品维表
ENUMS = ["单图", "多图", "单视频", "文本", "链接"]
#: 平台 —— ★ **以 Owner 任务 2 给的三个来源为准**（2026-10-23）：
#:   ① momcozy.com（官方独立站）② Amazon ③ TikTok（**已按 Owner 改回 YouTube**）
#: 上一轮我从库内 `渠道` 既有值推成「官网/Amazon/**YouTube**」，**第三个推错了** ——
#: 依据是任务 2 链接 3《Momcozy社媒账号盘点》第 51 行：
#: `Tiktok ｜ 北美 ｜ momcozyofficial ｜ https://www.tiktok.com/@momcozyofficial`。
#: 表里那 45 行已由 `rename_channel.py` 改正。教训：**平台名要问 Owner，不要从历史值反推** ——
#: 历史值只说明「以前采过什么」，不说明「今天要采什么」。
#: ★ 2026-10-23 第三次改：Owner 任务 2 指定「TikTok」，随后当场改口「**TikTok，换回 YouTube**」。
#: ⇒ 平台 = 官网 / Amazon / **YouTube**（这也是仓库既有惯例：
#: `采集-20261022/build_rows.py` 采的就是 YouTube @Momcozy，且 YouTube 实测可采、
#: TikTok 实测被地区重定向挡死 —— 见交付件「三源可行性」）。
CHANNELS = ["官网", "Amazon", "YouTube"]

# ── 任务给定的产品清单：品线 → 具体产品中文名（逐字来自 Owner 任务）
# ★ 2026-10-23 收窄：Owner 当场改为「**每个品线只采集 3 个具体产品**」，15 → 9。
#   被移出的 6 个（M6吸奶器 / V1 Pro吸奶器 / BW-NDT清洗机天然成分洗涤剂片 /
#   BS03全自动清洗消毒器洗涤块 / BM02婴儿监视器 / BM03婴儿监视器）已由
#   `trim_extra_products.py` 从表里删掉（清单 `deleted_extra_products.json`）。
#   **这份 SPEC 是产品清单的唯一真源** —— 删表、核验都从它（经 out_rows.json）取，
#   不许在别处再抄第二份。
#: ★★ 2026-10-23 第二次收窄（按 Owner 指令 + 官网实测）——
#:   Owner：「官网 momcozy.com 从下面选取有的。BW05、BW05配件替换成下面能用的两个
#:   （BS03 / BW-NDT洗涤剂片 / BS03洗涤块）；BM01 替换成 BM02 或 BM03」
#:   实测（products.json 240 条 + 逐条直试 handle）：
#:     BW05 / BW05配件 / BM01 / BM02 在官网 **0 命中**（BW05 的「英文名」本身是内部代号，
#:     创建于 2025-11-19；BW05配件 是售后备件；BM01 独立站已下架）
#:     BS03 与 BS03洗涤块 官网**只有 bundle 页**（独立页 handle 逐个 404）
#:     BW-NDT洗涤剂片 ✅ `momcozy-detergent-tablets-for-baby-bottle-washer`
#:     BM03 ✅ `5-5-inch-full-hd-smart-non-wifi-baby-monitorbm03s`（BM02 ❌，故取 BM03）
#:   ⚠️ 我的「英文名 token 匹配」曾把 BW-NDT 与 BM03 **误判成官网无**（前者英文名无数字、
#:     后者英文名根本不含 BM03）—— 这类判据必须人工复核，见交付件「我的错误」一节。
SPEC = [
    ("吸奶器", ["S12 Pro+吸奶器", "M5Smart吸奶器", "Air1吸奶器"]),
    ("清洗机", ["BS03全自动清洗消毒器", "BW-NDT清洗机天然成分洗涤剂片", "BS03全自动清洗消毒器洗涤块"]),
    ("婴儿监控器", ["BM03婴儿监视器", "BM08智能婴儿监视器", "BM04婴儿监视器"]),
]


def norm(s):
    """归一化只用于**匹配**；写进表里的值永远是商品维表的原值。"""
    return (s or "").replace(" ", "").replace("\u3000", "").lower()


def fetch_master():
    out, page = [], None
    while True:
        url = (f"{BASE}/bitable/v1/apps/{APP}/tables/{SRC_TABLE}/records"
               f"?page_size=500" + (f"&page_token={page}" if page else ""))
        r = _req(url, token())
        if r.get("code") != 0:
            raise SystemExit(f"读商品维表失败：{json.dumps(r, ensure_ascii=False)[:400]}")
        d = r["data"]
        out += d.get("items", [])
        if not d.get("has_more"):
            return out
        page = d.get("page_token")


def main():
    master = fetch_master()
    print(f"商品维表拉到 {len(master)} 行")

    prods = []
    for line, names in SPEC:
        for name in names:
            hit = [r for r in master if norm(r["fields"].get("产品中文名")) == norm(name)]
            if len(hit) != 1:
                raise SystemExit(f"❌ 精确匹配不唯一：{name!r} 命中 {len(hit)} 条 —— 整批不产出")
            f = hit[0]["fields"]
            spu, en = f.get("产品spu"), f.get("产品英文名")
            if not spu or not en:
                raise SystemExit(f"❌ {name!r} 的 spu/英文名 有缺项：spu={spu!r} en={en!r}")
            prods.append({"产品线": line, "产品中文名": f["产品中文名"],
                          "产品spu": spu, "产品英文名": en})

    assert len(prods) == 9, len(prods)

    rows = []
    # ★ 2026-10-23 Owner 定：数据采集要 3 个平台 ⇒ 矩阵再乘一维。
    #   行序 = **渠道优先**（官网 45 → Amazon 45 → YouTube 45），与仓库既有惯例一致：
    #   `采集-20261022/build_rows.py` 就是 `_site()` → `_amazon()` → `_youtube()` 这么排的，
    #   而且**采集本来就是按平台逐个抓的**，按平台分批最省事。
    #   要改成产品优先（每个产品 15 行连在一起）＝建表时调一下这两层循环的顺序，
    #   但**必须重建全部行**（Bitable 没有「移动记录」接口，顺序只能靠创建顺序）。
    for ch in CHANNELS:
        for p in prods:
            for e in ENUMS:
                rows.append({"fields": {**p, "渠道": ch, "内容类型": e}, "_meta": dict(p)})

    assert len(rows) == 135, len(rows)

    json.dump(rows, open("out_rows.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"产品 {len(prods)} 个 ｜ 枚举 {len(ENUMS)} ｜ 平台 {CHANNELS} "
          f"｜ 矩阵 {len(rows)} 行 → out_rows.json")
    for ch in CHANNELS:
        print(f"  {ch}: {len(prods)} 产品 × {len(ENUMS)} 枚举 = {len(prods) * len(ENUMS)} 行")
    print("\n逐字取自商品维表（供人核）：")
    for p in prods:
        print(f"  {p['产品线']:6s} {p['产品中文名']:22s} {p['产品spu']:20s} {p['产品英文名']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())