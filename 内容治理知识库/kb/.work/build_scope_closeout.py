#!/usr/bin/env python3
"""生成《交付-目标7-适用范围结案-20261012.md》。★ .md 走 `_safe_write`（node + 回读复核）。"""

from __future__ import annotations
import collections, json, os, sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
sys.path.insert(0, os.path.join(KB, ".work"))
sys.path.insert(0, os.path.join(KB, "l3"))
import _safe_write                                       # noqa: E402
import kb_rule_dimensions as D                           # noqa: E402

OUT = os.path.join(ROOT, "交付-目标7-适用范围结案-20261012.md")


def main() -> int:
    rows = [json.loads(l) for l in open(os.path.join(KB, "l3", "candidates", "rules.jsonl"),
                                       encoding="utf-8") if l.strip()]
    by = {}
    for r in rows:
        m = by.setdefault(r["rule_id"], {})
        for k, v in r.items():
            if v not in (None, "", [], {}):
                m[k] = v
    idx = D.build_l0_index()
    look = D.l0_lookup(idx)
    n = len(by)
    withs = [m for m in by.values()
             if any((m.get("applicable_scope") or {}).get(k)
                    for k in ("product_line", "channel", "content_type"))]
    gap = [m for m in by.values() if m not in withs]

    pl = collections.Counter()
    for m in by.values():
        for v in ((m.get("applicable_scope") or {}).get("product_line") or []):
            pl[str(v)] += 1

    tbl = collections.Counter()
    w1rules = []
    for m in gap:
        t, rec, _f = D.anchor_parts(m.get("anchor"))
        tbl[t] += 1
        f, _ = look(m)
        v = (f or {}).get("卖点ID")
        if isinstance(v, dict):
            v = v.get("value")
        if isinstance(v, list):
            v = v[0] if v else None
        if v:
            w1rules.append((m.get("rule_id"), str(v)))

    A, L = None, []
    L.append("# 交付 · 目标 7「适用范围」结案（本地已尽，缺口在源侧）")
    L.append("")
    L.append("> 对应：xlsx **A6 行（10/12–10/16）G 列「必须做」第 2 条**（目标 7 适用范围）。")
    L.append("> 判据（xlsx 逐字）：「给每条规则补『适用产品线 / 渠道 / 内容类型』」（PRD §6.5）。")
    L.append("> 本件**做了什么、以及为什么剩下的做不了**，逐表给证据。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 一、结论")
    L.append("")
    L.append("**509 条规则里，能补的已全部补上；剩下的 401 条不是「没做」，是「源表里没有那一列」。**")
    L.append("")
    L.append("| | 改前 | **改后** |")
    L.append("|---|---|---|")
    L.append("| 有适用范围的规则 | 89 | **%d** |" % len(withs))
    L.append("| 无任何范围 | 420 | **%d** |" % len(gap))
    L.append("")
    L.append("**本轮补上的 %d 条 —— 依据是「向既有口径对齐」，不是新造口径**：" % len(w1rules))
    L.append("")
    L.append("`W1卖点表达边界（品线反馈0910）` 表的 `卖点ID = \"W1-03\"`，取 `-` 前段得产品代号 `W1`。")
    L.append("凭什么是 `W1`（三条依据）：")
    L.append("1. 表名逐字就是 `W1卖点表达边界`，`来源` 字段逐字写「**品线反馈**截图 2026-09-10」；")
    L.append("2. **既有 89 条有范围规则的 `product_line` 取值本来就是这类代号**（改后实测：")
    L.append("   `%s`）⇒ 取 `W1` 是**对齐**；" % " / ".join("%s %d" % kv for kv in pl.most_common(8)))
    L.append("3. 写**整值** `W1-03` 会把卖点序号塞进品线列，下游按品线筛**筛不到**。")
    L.append("")
    L.append("## 二、剩下 %d 条为什么推不出（逐表给证据）" % len(gap))
    L.append("")
    L.append("| 来源表 | 条数 |")
    L.append("|---|---|")
    for k, v in tbl.most_common():
        L.append("| `%s` | %d |" % (k, v))
    L.append("")
    L.append("**该表的全部字段**（逐字，读自 `kb/l0/records/`）：")
    L.append("")
    L.append("```")
    for t, _ in tbl.most_common(2):
        ks = set()
        for (st, rec), f in idx.items():
            if st == t:
                ks |= set(f)
        L.append("[%s]" % t)
        for k in sorted(ks):
            L.append("   · %s" % k)
    L.append("```")
    L.append("")
    L.append("⇒ **没有任何产品线 / 适用产品 / 适用型号 / 渠道 / 平台列。**")
    L.append("")
    L.append("⚠️ **`文章标题` 不是品线**（这一条必须写死，否则以后一定有人去拿它补）：")
    L.append("实测该表 **134 种标题全是科普选题** —— 「产后漏尿：什么情况可以观察…」「孕期产检清单」")
    L.append("「心情不好会影响泌乳吗？」「生理性涨奶不用慌」「把握产后黄金一小时：皮肤接触与正确衔乳」…")
    L.append("它们是**内容主题**，不是**产品线**。拿它补 = 编。")
    L.append("")
    L.append("## 三、已落成的登记（不只活在这份文档里）")
    L.append("")
    L.append("| 落点 | 内容 |")
    L.append("|---|---|")
    L.append("| `kb/l3/registry/dimension-policy.json` | 四维链 + `applicable_scope_sources` 新增 `卖点ID` ＋ `SCOPE_VALUE_PREFIX` 说明 |")
    L.append("| `kb/l3/kb_rule_dimensions.py → NOT_DERIVABLE` | 新增 `applicable_scope.product_line` / `applicable_scope.channel` 两条，写明「源侧缺列」与「不许拿标题猜」 |")
    L.append("| `kb/l3/registry/l3.json changes[]` | run_id 登记（可回退） |")
    L.append("")
    L.append("## 四、判据与尺子")
    L.append("")
    L.append("| 判据 | 结果 |")
    L.append("|---|---|")
    L.append("| `kb_rule_dimensions --selftest` | **55/55**（原 52；新增 ②f–j 卖点ID 前缀 ＋ ⑤j–l 占位字典算空） |")
    L.append("| ②f 取前缀（不是整值） | ✅ |")
    L.append("| ②g 反向对照：清空前缀表 ⇒ ②f 精确变红 | ✅（已实测） |")
    L.append("| ②i 前缀取空（`-03`）⇒ 落空不编 | ✅ |")
    L.append("| ②j 与既有源并存时都收（不丢 `适用产品`） | ✅ |")
    L.append("| ⑤k 反向对照：**有真实值就不算空**（不许顺手覆盖） | ✅ |")
    L.append("| **逐字节幂等**：日更 `apply_dimensions(mode=\"force\")` 重算后 sha256 不变 | ✅ `6c0b8820af270c16…` |")
    L.append("| `workflow_smoke` / `envelope_census` / `check_source_readonly` / `l3_gate` / `regression_gate` | 全 exit 0 |")
    L.append("")
    L.append("**影响面**：`applicable_scope` 全库**没有任何活消费者**（`grep` 只命中两处注释），")
    L.append("守衡侧也不读它 ⇒ 本次改动**零工作流影响**。")
    L.append("")
    L.append("## 五、过程中修掉的一处**同类老 bug**（值得单说）")
    L.append("")
    L.append("回填器第一次预演时，这 19 条**填不进去** —— 被报成「不一致、保留原值」。")
    L.append("根因：`applicable_scope` 的现值是**占位字典**")
    L.append("`{\"product_line\": None, \"channel\": None, \"content_type\": None, \"_derivation\": None}`")
    L.append("—— **语义上一格都没填，结构上却是非空字典** ⇒ 过不了「空」的判据 ⇒ **回填永远不生效**。")
    L.append("")
    L.append("这与库里 2026-10-10 栽过的「**哨兵 `unknown` 被当成已有值** ⇒ 509 条全报冲突、一个字段都没填上」")
    L.append("**是同一类病**：把「还没填」的占位当成了「已填」。")
    L.append("⇒ 已修（`_is_placeholder_scope()`），并钉了 ⑤j（算空）＋ **⑤k 反向对照**（有真实值仍不许覆盖）。")
    L.append("")
    L.append("## 六、要你裁的一件（带推荐）")
    L.append("")
    L.append("剩下 401 条里，另有 **19 条**的**规则正文逐字含「吸奶器」**（源字段仍无范围列）。")
    L.append("")
    L.append("- **我不推荐补**。理由：那是「**从正文推**」—— 而 `dimension-policy.json` 对 `modality`")
    L.append("  **明确拒绝过这种推法**（实测「文字 139 : 图片 6 : 视频 5」且那 6/5 是同一句说明，")
    L.append("  不是规则本身的模态）。同一条纪律要对自己一致：**正文提到 ≠ 这条规则的适用范围**。")
    L.append("  代价：这 19 条继续留空，直到源侧补列。")
    L.append("- 备选：认「正文逐字含品线词」也算声明 ⇒ 多 19 条有值。**代价**：口径一放开，")
    L.append("  下一批「正文含吸奶器」的可能有 200 条，而其中一部分只是**举例**不是**范围** ⇒")
    L.append("  **错值比空值更坏**（空值人会去补，错值人不会回头看）。")
    L.append("")
    L.append("## 七、真正的解法（一句话，交出去）")
    L.append("")
    L.append("**请源侧在 `专家修订汇总表` 加两列：「适用产品线」「适用渠道」。**")
    L.append("源表只读，本地补不了；加完列后**一条命令**即可回填：")
    L.append("")
    L.append("```")
    L.append("sh kb/kbpy .work/backfill_dimensions.py    # 幂等；已有真实值不会被覆盖")
    L.append("```")
    L.append("")
    L.append("## 八、回退")
    L.append("")
    L.append("```")
    L.append("/bin/cp kb/l8/_archive/dim-backfill-scope-v3-20261012-1122/rules.jsonl.before \\")
    L.append("        kb/l3/candidates/rules.jsonl    # sha256 回到 f902c9b0c84bc41d…")
    L.append("```")
    L.append("归档链：`3f7d50dc…`（原始）→ `f1db7e54…` → `f902c9b0…` → **`6c0b8820…`（现行）**。")
    L.append("**不要只回退数据不回退代码** —— ②f / ⑤j 会立刻变红（那正是它们该有的行为）。")
    L.append("")

    text = "\n".join(L)
    _safe_write.write_text(OUT, text)
    print("已落盘：%s" % OUT)
    print("回读：%d 字节 / %d 行" % (os.path.getsize(OUT), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
