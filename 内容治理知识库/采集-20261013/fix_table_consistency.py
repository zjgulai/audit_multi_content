#!/usr/bin/env python3
"""③ 修表行与它自己那份报告文档的不一致（8 行）。

## 为什么以**文档**为准

表行的 `状态/Agent 结论/问题数量` 是**机器写回**的派生列；文档是**发出去的那一份**，
是人点开看到的东西。两者打架时，以文档为准 —— 修完「点开报告」与「表里读数」同源。

## 逐行目标值（来自 `out/reports80.json` 实拉解析）

| 内容 ID | 表(修前) | 文档 | 修后 |
|---|---|---|---|
| MC-US-AMZ-B0D4QV8DSP-IMG | PASS/0 | REVIEW/5 | REVIEW/5 |
| MC-US-WEB-COL-electric-breast-pump | REVIEW/7 | NEEDS_INPUT/— | 待审 / NEEDS_INPUT / 空 |
| MC-US-WEB-COL-hospital-grade-breast-pump | REVIEW/7 | NEEDS_INPUT/— | 待审 / NEEDS_INPUT / 空 |
| MC-US-AMZ-B0FHQJWPTN | REVIEW/6 | NEEDS_INPUT/— | 待审 / NEEDS_INPUT / 空 |
| MC-US-YT-88uvcSNxMdk | 待审/1 | NEEDS_INPUT/— | 待审 / NEEDS_INPUT / 空 |
| MC-US-WEB-IMG-8865918910662 | REVIEW/5 | REVIEW/4 | REVIEW/4 |
| MC-US-AMZ-B0CWLHKQNT | REVIEW/5 | REVIEW/7 | REVIEW/7 |
| MC-US-AMZ-B0H6Q2G76Z | REVIEW/3 | REVIEW/5 | REVIEW/5 |

## 两条口径（写进代码，别靠记）

1. **`状态` 列没有 `NEEDS_INPUT` 这个选项**（只有 待审/PASS/REVIEW/BLOCK/已修改/已发布）
   ⇒ 拒答落 `待审`（＝等人看）。这也与库内既有落法一致（「state=NEEDS_INPUT 落 NEEDS_INPUT/待审」）。
2. **拒答行的 `问题数量` 一律清空（null），不写 0。**
   写 0 会被读成「没有问题」—— 而拒答的语义是「**未判**」。
   库内栽过一次同类误读（「拒答被当成 0 条」），不重蹈。
"""
import json, os, re, subprocess, sys, datetime

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblavfbMDMeRsulo"
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def main(apply=False):
    rows = []
    for line in open(os.path.join(OUT, "tbl80_now.ndjson"), encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rep = json.load(open(os.path.join(OUT, "reports80.json")))
    docs = {x["doc"]: x for x in rep["docs"]}

    plan, backup = [], []
    for r in rows:
        toks = re.findall(r"docx/([A-Za-z0-9]{20,})", str(r.get("报告链接") or ""))
        doc = docs.get(toks[0]) if toks else None
        if not doc:
            continue
        concl, dn = doc["doc_concl"], doc["doc_n"]

        def flat(v):
            """select 字段读回来是**列表**（`['REVIEW']`），text/number 是标量 —— 统一成字符串再比。

            ★ 踩过的坑：拿 `['REVIEW']` 直接跟 `'REVIEW'` 比 ⇒ 永远不等 ⇒ 80 行全被误判成「要改」。
            """
            if isinstance(v, list):
                return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
            return "" if v is None else str(v)

        cur_st, cur_ag, cur_n = flat(r.get("状态")), flat(r.get("Agent 结论")), flat(r.get("问题数量"))

        tgt_st = "待审" if concl == "NEEDS_INPUT" else concl
        tgt_ag = concl
        tgt_n = None if concl == "NEEDS_INPUT" else dn      # 拒答 ⇒ 清空，不写 0

        if cur_st == tgt_st and cur_ag == tgt_ag and cur_n == flat(tgt_n):
            continue
        fields = {"Agent 结论": tgt_ag, "状态": [tgt_st]}
        fields["问题数量"] = tgt_n if tgt_n is not None else None
        rec = {"record_id": r["record_id"], "fields": {k: v for k, v in fields.items()}}
        plan.append(rec)
        backup.append({"record_id": r["record_id"], "内容 ID": r.get("内容 ID"),
                       "before": {"状态": cur_st, "Agent 结论": cur_ag, "问题数量": cur_n},
                       "after": {"状态": tgt_st, "Agent 结论": tgt_ag, "问题数量": tgt_n}})

    print(f"待修 {len(plan)} 行：")
    for b in backup:
        print(f"   {b['内容 ID']:<34} {b['before']} → {b['after']}")

    if not apply:
        print("\n[预演] 未写盘。加 --apply。")
        return
    os.makedirs(os.path.join(HERE, f"backup_table_fix_{STAMP}"), exist_ok=True)
    json.dump(backup, open(os.path.join(HERE, f"backup_table_fix_{STAMP}",
                                        "before_after.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"\n原值备份 -> 采集-20261013/backup_table_fix_{STAMP}/before_after.json")

    # ★ 载荷形状：`{"update_records": {<record_id>: {字段: 值}}}` —— **映射**，不是 {record_id, fields} 列表。
    #   实测踩过：写成列表 ⇒ CLI 不报错、stdout 直接是空的（看着像"成功"，其实什么都没改）。
    body = {"update_records": {rec["record_id"]: rec["fields"] for rec in plan}}
    p = subprocess.run([LARK, "base", "+record-batch-update", "--base-token", BASE,
                        "--table-id", TABLE, "--profile", "dsh-kb", "--as", "bot",
                        "--json", json.dumps(body, ensure_ascii=False)],
                       capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if not out:
        print(f"  ❌ 无输出（退出码 {p.returncode}）stderr={err[:300]}")
        return
    try:
        d = json.loads(out[out.find("{"):])
    except Exception:
        print("  ❌ 非 JSON:", out[:300]); return
    print(f"  {'✅' if d.get('ok') else '❌'} 批量更新 {len(plan)} 行  {d.get('error') or ''}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
