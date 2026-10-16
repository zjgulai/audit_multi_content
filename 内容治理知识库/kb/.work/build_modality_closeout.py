#!/usr/bin/env python3
"""生成《交付-目标8-模态结案-20261012.md》。★ .md 走 `_safe_write`（node + 回读复核）。"""

from __future__ import annotations
import collections, json, os, sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
sys.path.insert(0, os.path.join(KB, ".work"))
sys.path.insert(0, os.path.join(KB, "l3"))
import _safe_write                                       # noqa: E402
import kb_rule_dimensions as D                           # noqa: E402

OUT = os.path.join(ROOT, "交付-目标8-模态结案-20261012.md")


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
    und = sum(1 for m in by.values() if str(m.get("modality")) == D.MODALITY_UNDETERMINED)

    af = collections.Counter()
    for m in by.values():
        t, rec, fld = D.anchor_parts(m.get("anchor"))
        af["%s / %s" % (t, fld)] += 1

    tabs = collections.Counter(D.anchor_parts(m.get("anchor"))[0] for m in by.values())

    def fields(t):
        ks = set()
        for (st, rec), f in idx.items():
            if st == t:
                ks |= set(f)
        return sorted(ks)

    L = []
    A = L.append
    A("# 交付 · 目标 8「模态」结案（本地穷尽，缺口在源侧）")
    A("")
    A("> 对应：xlsx **A6 行（10/12–10/16）G 列「必须做」第 3 条**（目标 8 模态）。")
    A("> PRD §6.5 逐字要每条规则带「适用产品线 / 渠道 / **内容类型**」；§5.2 的内容类型 = 文字 / 图片 / 视频。")
    A("> 与《交付-目标7-适用范围结案-20261012.md》同一形状：**能补的补、补不了的逐条给证据**。")
    A("")
    A("---")
    A("")
    A("## 一、结论")
    A("")
    A("**%d 条规则，模态**一条都推不出 **—— 不是「没做」，是「源里没有那一格」。**" % len(by))
    A("")
    A("| | 值 |")
    A("|---|---|")
    A("| `modality` = `undetermined` | **%d / %d（100%%）** |" % (und, len(by)))
    A("| 能从源字段确证的 | **0** |")
    A("")
    A("## 二、四条取证（缺一条都不算查过）")
    A("")
    A("### ① 5 张锚点表的字段**逐个列过**，没有一张有媒体列")
    A("")
    for t, _ in tabs.most_common():
        fs = fields(t)
        A("- **`%s`**（%d 字段）：%s" % (t, len(fs), " / ".join(fs)))
    A("")
    A("⇒ `广告文案明细` 那 27 个字段里，唯一沾边的是 `落地页URL`（**不是媒体列**）。")
    A("")
    A("### ② 锚点**字段名** 0 个含媒体专名")
    A("")
    A("实测全库只有 **%d 种**锚点（表 / 字段）：" % len(af))
    A("")
    for k, v in af.most_common():
        A("- `%s` — %d 条" % (k, v))
    A("")
    A("⇒ 一个「图片 / 视频 / 素材」都没有。")
    A("")
    A("### ③ ★ 关键发现：**信号在库里，只是不在规则的路径上**")
    A("")
    A("全库**唯一**有媒体字段的表是 **`负面样本`**：")
    A("")
    A("| 字段 | 实测取值 |")
    A("|---|---|")
    A("| `素材类型` | **图片 168 ／ 文字 2**（2 种） |")
    A("| `图片素材` | 有值 114 ／ 空 55（file_token 形式） |")
    A("| `视频素材` | **全部为空**（170/170） |")
    A("| `文字素材` | 有值 7 ／ 空 163 |")
    A("")
    A("**而 0 条规则锚在 `负面样本`。** 规则锚点分布：")
    A("")
    for k, v in tabs.most_common():
        A("- `%s` — %d 条" % (k, v))
    A("")
    A("⇒ 这一条**可以直接交出去**：要么源侧给这 5 张规则表补媒体列，")
    A("要么让「反例条款」（`负面样本` → L4 的 S-1 段）也进规则层 —— **后者是产品口径，不是我们能定的**。")
    A("")
    A("### ④ 正文模态词**已实测不可靠**")
    A("")
    A("（沿用既有实测）扫规则正文的「文字 / 图片 / 视频」三个词：139 : 6 : 5，")
    A("且那 6/5 是同一句『文案为空 / 非文本广告』的说明，**不是规则本身的模态**。")
    A("")
    A("## 三、候选口径（**两条，都要你签；我没执行**）")
    A("")
    A("### 候选 A：`广告文案明细.广告类型` —— 覆盖 **16 条**")
    A("")
    A("该字段实测取值（**这一格此前从没查过**）：")
    A("")
    A("| 取值 | 条数 | 能不能判模态 |")
    A("|---|---|---|")
    A("| `自适应搜索广告` | 84 | 文字 |")
    A("| `图片需求开发广告` | 83 | 图片 |")
    A("| `产品广告` | 55 | **判不了**（载体不明） |")
    A("| `视频需求开发广告` | 31 | 视频 |")
    A("| （空） | 29 | 判不了 |")
    A("")
    A("**但它要先答一个问题**：规则的正文是 `Primary Text` / `Headline`（**文案**），")
    A("而它所属的**广告**是视频 —— **「这条文案规则算不算视频规则」是口径，不是机械补丁。**")
    A("")
    A("### 候选 B：按来源性质默认 `text` —— 覆盖 **最多 493 条**")
    A("")
    A("四张主要来源表（专家修订汇总表 401 ＋ 风险文案改写建议库 52 ＋ 品线内容边界规则库 21 ＋ W1 表 19）")
    A("的锚点字段分别是「修订位置（原文引用）」「风险原句示例」「边界内容」「建议表达（合规话术）」")
    A("—— **全都是在改「文字怎么写」**。")
    A("")
    A("⚠️ 但这是**从来源性质推**，不是源字段声明；而 PRD §6.5 要的是**规则自己的**适用内容类型。")
    A("")
    A("### ```我的推荐```")
    A("")
    A("**推荐：两条都先不签，维持 `undetermined`，把缺口交回源侧。**")
    A("")
    A("- **理由**：本库对同一件事有一条成文纪律 —— 本模块抬头逐字写着")
    A("  「**不编。**源里取不到的，落 `None`＋写出处；**不许**用常识补齐」。")
    A("  候选 A 与 B **都是「推」**（一个推载体、一个推来源性质），不是「取」。")
    A("  而且 `modality` **全库零消费者**（同 `applicable_scope`，只被两处注释提到）——")
    A("  **现在写进去也没人用**，写错的代价却是永久的（错值人不会回头看）。")
    A("- **代价**：PRD §6.5 的「内容类型」这一格**继续空着**，验收时只能如实说「源侧未提供」。")
    A("  ⇒ 这一条要写进《未达标说明》。")
    A("")
    A("**如果你要一个「有值」的结果**，我推荐只签 **候选 A**（不是 B）：覆盖面小（16 条）、")
    A("取值是**受控枚举**（图片/视频/搜索三类，不是我推的）、且**它自己就是源字段**。")
    A("代价：要先回答「文案规则算不算视频规则」—— 建议口径是「**按广告载体**」（因为 PRD §5.2 的模态")
    A("描述的就是素材形态），那这 16 条里 31/198 会落 `video`。")
    A("")
    A("## 四、已落成的登记")
    A("")
    A("| 落点 | 内容 |")
    A("|---|---|")
    A("| `kb/l3/kb_rule_dimensions.py → NOT_DERIVABLE` | 重写 `modality`（四条取证）＋ 新增 `modality.candidate_ads_type` / `modality.candidate_text_default` |")
    A("| `kb/l3/registry/dimension-policy.json` | 上面三条**全部**流进 `honest_limits`（现 7 条）—— 政策件才是**给人的那一份** |")
    A("| `kb/l3/registry/l3.json changes[]` | run_id 登记 |")
    A("")
    A("**⚠️ 一个必须说清的副作用**：`modality_basis` 是**逐行写进每条规则**的（本模块的设计：每个值带出处），")
    A("所以**改这段说明文字 = 改 1018 行数据**（文件 3.69MB → 3.76MB）。")
    A("好处是出处跟着数据走；坏处是**文档改动会触发数据重写**，看 diff 时别误以为口径变了。")
    A("")
    A("## 五、尺子")
    A("")
    A("| 判据 | 结果 |")
    A("|---|---|")
    A("| `kb_rule_dimensions --selftest` | **55/55** |")
    A("| `--probe`（只读） | `modality 可用 0/509`；`applicable_scope` 缺口 401 |")
    A("| `workflow_smoke` / `envelope_census` / `check_source_readonly` / `l3_gate` | 全 exit 0 |")
    A("| **逐字节幂等** | `92694e86bc2f4964…`（重复回填内容无改动） |")
    A("")
    A("## 六、回退")
    A("")
    A("```")
    A("/bin/cp kb/l8/_archive/dim-backfill-modality-closeout-20261012-1129/rules.jsonl.before \\")
    A("        kb/l3/candidates/rules.jsonl    # sha256 回到 6c0b8820af270c16…")
    A("```")
    A("归档链：`3f7d50dc…` → `f1db7e54…` → `f902c9b0…` → `6c0b8820…` → **`92694e86…`（现行）**。")
    A("")

    text = "\n".join(L)
    _safe_write.write_text(OUT, text)
    print("已落盘：%s" % OUT)
    print("回读：%d 字节 / %d 行" % (os.path.getsize(OUT), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
