#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删掉 `采集数据` **只有 `【说明】` 备注、没有真实素材**的行（Owner 2026-10-23 决定）。

## 删什么

`采集数据` 含 `【说明】` 的行 —— 即「该源确实没有这个产品的素材」，
备注已经说明原因，但**没有可测内容**。实测 24 行（表 135 → 111）。

⚠️ 严格意义的「采集数据完全空」是 **0 行** —— 上一轮已把空的全写成备注了。
所以「未采集到」只有取这个口径才有东西可删；两个口径的差别已在对话里确认过。

## 为什么删（不只是「看起来干净」）

这 24 行留着有**具体风险**：下游（守衡 / 评审引擎）若把 `采集数据` 当素材，
就会把 `【说明】产品无视频` 这句话**当成内容送去审**。

## 不可逆 —— 所以先快照

Bitable **没有撤销**（本会话早前删过的 46 行再没回来）。所以：
1. 先把每行**完整字段**写进 `snapshot_note_rows_20261023.json`；
2. 再把「删哪些、为什么」写进 `removed_combos_20261023.json`（判据统一认它，见 `removed_rows.py`）；
3. 最后才删，删完逐个 record_id 核对**已不存在**，并核对总数 135 → 111。

用法：
  python3 delete_note_rows.py            # 预演
  python3 delete_note_rows.py --apply
"""
import json
import sys

sys.path.insert(0, "../../tools")
sys.path.insert(0, ".")
import removed_rows as RR                                        # noqa: E402
from lark_find import _req, token, BASE                          # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
MINE_PREFIXES = ("reczz28QhOqu", "reczz28QhOte")
MARK = "【说明】"
SNAP = "snapshot_note_rows_20261023.json"


def fetch_all():
    out, page = [], None
    while True:
        url = (f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=500"
               + (f"&page_token={page}" if page else ""))
        d = _req(url, token())["data"]
        out += d.get("items", [])
        if not d.get("has_more"):
            return out
        page = d.get("page_token")


def main():
    apply_ = "--apply" in sys.argv
    rows = fetch_all()
    mine = [r for r in rows if r["record_id"].startswith(MINE_PREFIXES)]
    targets = [r for r in mine if MARK in (r["fields"].get("采集数据") or "")]

    print(f"表内 {len(rows)} 行 ｜ 本批 {len(mine)} 行")
    print(f"待删（采集数据只有 {MARK} 备注、无真实素材）：**{len(targets)} 行**")
    print(f"删后本批行数：{len(mine)} → {len(mine) - len(targets)}\n")
    if not targets:
        print("✅ 没有符合的行，无需删除")
        return 0

    by = {}
    for r in targets:
        c = r["fields"].get("渠道")
        by[c] = by.get(c, 0) + 1
    print(f"按平台：{by}")
    for r in targets:
        f = r["fields"]
        print(f"   - {f.get('渠道'):8s} {f.get('产品中文名'):26s} {f.get('内容类型'):5s} {f.get('采集数据')}")

    if not apply_:
        print("\n（预演，未删；要真删加 --apply）")
        return 0

    # ① 快照（删前）
    json.dump([{"record_id": r["record_id"], "fields": r["fields"]} for r in targets],
              open(SNAP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n① 已快照 {len(targets)} 行 → {SNAP}")

    # ② 声明（删前）—— 判据统一认它
    decl = {"removed": [{"record_id": r["record_id"], "fields": r["fields"]} for r in targets],
            "count": len(targets),
            "why": ("Owner 2026-10-23：采集数据只有【说明】备注、没有真实素材的行删掉；"
                    "严格『完全空』是 0 行，故取『只有备注』口径。"
                    "风险：留着会被下游把备注当素材送审。不可逆，已快照。"),
            "snapshot": SNAP,
            "before": len(mine), "after": len(mine) - len(targets)}
    json.dump(decl, open(RR.DECL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"② 已声明移除 {len(targets)} 个组合 → {RR.DECL}")

    # ③ 删
    ids = [r["record_id"] for r in targets]
    for i in range(0, len(ids), 100):
        part = ids[i:i + 100]
        r = _req(f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records/batch_delete",
                 token(), {"records": part})
        if r.get("code") != 0:
            print("❌ 删除失败:", json.dumps(r, ensure_ascii=False)[:400])
            return 1
        print(f"③ 已删 {i + len(part)}/{len(ids)}")

    # ④ 核对：每个 record_id 都不在了；总数对得上
    after = fetch_all()
    alive = {r["record_id"] for r in after}
    still = [i for i in ids if i in alive]
    mine_after = [r for r in after if r["record_id"].startswith(MINE_PREFIXES)]
    print(f"\n④ 核对：残留 {len(still)} 行（应为 0）｜ 本批 {len(mine_after)} 行"
          f"（应为 {len(mine) - len(targets)}）")
    ok = not still and len(mine_after) == len(mine) - len(targets)
    print("✅ 删除完成" if ok else "❌ 核对不符")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())