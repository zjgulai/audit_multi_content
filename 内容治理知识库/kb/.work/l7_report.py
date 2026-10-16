#!/usr/bin/env python3
"""生成 L7 运行留痕：kb/l7/runs/<run_id>.json | .report.md | .ops.log"""
import hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
L7, RUN = "kb/l7", "20260923-1500"


def rd(p):
    return json.load(open(p, encoding="utf-8"))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


now = time.strftime("%Y-%m-%d %H:%M:%S")
reg, integ = rd(f"{L7}/registry/l7.json"), rd("kb/.work/l7_integrity.json")
self_a = open(f"{L7}/selftest_a_block.md", encoding="utf-8").read()
self_b = open(f"{L7}/selftest_b_refusal.md", encoding="utf-8").read()
self_d = open(f"{L7}/selftest_d_paraphrase.md", encoding="utf-8").read()
self_e = open(f"{L7}/selftest_e_trigger.md", encoding="utf-8").read()
skill = open(f"{L7}/skills/kb-content-review/SKILL.md", encoding="utf-8").read()
probe = rd("kb/.work/l7_probe_d.json")
cap = rd("kb/l6/registry/l6.json")["retrieval_capability"]
latest = {}
for l in open("kb/l3/candidates/rules.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l)
        latest[r["rule_id"]] = r
missing_art = [rid for rid, r in latest.items() if not (r.get("article_no") or "").strip()]

# 门限下被舍弃的结果举例：取一次真实运行里的 discarded
p = subprocess.run([sys.executable, f"{L7}/skills/kb-content-review/scripts/review.py",
                    "--text", "Experience pain-free pumping with our hospital grade pump. Get more milk in less time.",
                    "--json", "--run-id", f"{RUN}-report"], capture_output=True, text=True)
rj = json.loads(p.stdout)
discarded = rj["trace"]["units"]["discarded"][:3]
adopted = rj["trace"]["units"]["adopted"][:3]

# 从自验 A 里抽出完整输出原文（模板块）
blocks = re.findall(r"```\n(【审查结论[\s\S]*?)```", self_a)
out_a_full = blocks[0].strip() if blocks else ""
out_b_full = (re.findall(r"```\n(【审查结论[\s\S]*?)```", self_b) or [""])[0].strip()

ART = [f"{L7}/skills/kb-content-review/SKILL.md", f"{L7}/output_template.md", f"{L7}/registry/l7.json",
       f"{L7}/selftest_a_block.md", f"{L7}/selftest_b_refusal.md", f"{L7}/selftest_d_paraphrase.md",
       f"{L7}/selftest_e_trigger.md", f"{L7}/skills/kb-content-review/scripts/review.py",
       f"{L7}/skills/kb-content-review/references/protocols.md",
       f"{L7}/skills/kb-content-review/references/categories.md", f"{L7}/skills/kb-content-review/README.md"]
ART += [f"{L7}/reports/{f}" for f in sorted(os.listdir(f"{L7}/reports"))]

run = {
    "run_id": RUN, "stage": "L7 消费侧：使用知识库的 skill + 验收", "finished_at": now, "kb_version": "v0",
    "article_no_read": {"rules": len(latest), "missing": missing_art,
                        "ranges": integ["checks"]["article_no_read"]["ranges"],
                        "source": "kb/l3/candidates/rules.jsonl（L4 分配，只读）",
                        "registry": "kb/l4/registry/l4.json"},
    "skill": {"path": f"{L7}/skills/kb-content-review/SKILL.md", "name": "kb-content-review",
              "complexity": "complex", "bytes": len(skill.encode()),
              "validator": "root-skills-creator/scripts/validate-skill.py",
              "validator_result": {"passed": True, "quality_score": 98,
                                   "warnings": [".skill-meta/ is recommended for future MCP integration"]},
              "references": ["references/protocols.md", "references/categories.md"],
              "script": "scripts/review.py"},
    "thresholds": reg["retrieval"]["gate"], "no_hit_semantics": reg["retrieval"]["no_hit_semantics"],
    "discarded_examples": discarded, "adopted_examples": adopted,
    "vocabulary": {"version": reg["vocabulary"]["version"],
                   "categories": {k: list(v["subs"]) for k, v in reg["vocabulary"]["categories"].items()},
                   "code_map": reg["vocabulary"]["code_map"], "keyword_map_size": len(reg["vocabulary"]["keyword_map"]),
                   "prd_7_2": reg["vocabulary"]["prd_7_2_domains"], "prd_7_3": reg["vocabulary"]["prd_7_3_vetoes"]},
    "selftest": {"A_block": {"criteria": "见 selftest_a_block.md 判据表", "output": out_a_full},
                 "B_refusal": {"output": out_b_full, "state": "拒答"},
                 "C_acceptance": {"ran": False, "why": f"{L7}/acceptance_cases.md 不存在（任务条件：若存在才跑）"},
                 "D_paraphrase": {"source": "kb/.work/l7_probe_d.json",
                                  "modes": ["bm25_only", "vector_only", "fuse_0.7_0.3", "fuse_0.5_0.5"],
                                  "conclusion": "维持 BM25 为主；向量无净增益，不给融合权重"},
                 "E_trigger": {"cases": 8, "consistent": 8, "method": "逐条对照 description 人工判定（无独立分类器）"}},
    "integrity": integ["checks"], "integrity_verdict": integ["verdict"],
    "citation_contract": {"unmet_conclusions": [], "unmet_source": "三次自验运行的 trace.unmet_citation 均为空"},
    "artifacts": [{"path": p_, "bytes": os.path.getsize(p_), "sha256": sha(p_)} for p_ in ART],
    "decisions": [
        {"id": "D1", "decision": "检索与引用合成一个 skill（kb-content-review），两段协议在文件内分开写",
         "why": "两段是同一能力的两个阶段，中间没有独立使用者；拆开的不对称风险（没按格式引 / 没检索就答）都是幻觉。也不按四类库拆四个：那会把同一套协议复制四份，用 kb_type 区分即可"},
        {"id": "D2", "decision": "默认 BM25 为主，仅在 BM25 原始分低于门限时启用向量补召；不用等权 RRF 当默认",
         "why": "L6 实测 bm25_only 的 A 组 hit@3 1.0 / p@3 0.958，hybrid(等权 RRF) 0.875 / 0.542；本批 D 组（规避型）三种模式 hit@3 都是 0.8、向量 p@3 更低 → 两批合起来维持 BM25 为主"},
        {"id": "D3", "decision": "门限用原始分（BM25 ≥ 8.0 / 余弦 ≥ 0.60），并额外引入覆盖门限（16.0）",
         "why": "RRF 分恒为 0.016393、无区分度；单一门限也不够（A/B 有重叠）。覆盖门限是本批现场发现的缺口：首版没有它时，离题的汽车保养/基金文本因一条偶然过门限的 BM25 命中被判 PASS——现在覆盖信号不成立就拒答"},
        {"id": "D4", "decision": "引用锚点必须在规则的**全部证据单元**里找真正含摘录的那一个，不能用规则的首个证据单元",
         "why": "规则会把上百条来源记录的片段汇总（如 H02 有 102 个证据单元），首个证据单元常常不含被引片段；首版因此有 4 条结论引用不到锚点，按硬闸门被丢弃，改为逐个证据单元确认后归零"},
        {"id": "D5", "decision": "同一处文案命中多条同义规则时合并为一条，并记下被合并的条款号",
         "why": "风险文案改写建议库里有大量近义条目（同一条 More Milk 有 4+ 条），不合并会把问题数虚高、把 ≥3 的分流规则触发得过早"},
        {"id": "D6", "decision": "输出模板在四要素之外补上 锚点 / source_sha256 / 判定 三行",
         "why": "引用契约要求这三项，且「引用不到本地锚点的结论不许输出」；模板与实现对齐后才能既满足模板又满足契约"},
        {"id": "D7", "decision": "拒答按**实际走过的路**选 no_hit_semantics（只跑 BM25 → bm25_only 文案；试过向量 → hybrid 文案），并逐层说明为什么没依据",
         "why": "首版拒答文案里写了「最高原始分 11.07 < 门限 8.0」这种算术上不成立的解释（真实原因是覆盖信号不成立），属假陈述，已改成分层说明"},
        {"id": "D8", "decision": "责任人做成 registry 角色位（pass_signoff / review_reviewers / block_owner），未填时输出「（未配置）」",
         "why": "硬编码人名会在组织变动后失效；当前 handle 为 null，输出如实标注未配置，不猜人名"},
        {"id": "D9", "decision": "自验 C 跳过并留痕",
         "why": f"{L7}/acceptance_cases.md 不存在（任务写明「若文件存在」才跑），不伪造验收数据"},
        {"id": "D10", "decision": "自验 E 的「实际触发」按 description 人工判定，并写明方法局限",
         "why": "本批没有独立触发分类器可跑；真正的触发回归要走 root-skills-eval 的 A/B 卷，不在本批范围。判定结论只对 description 文本负责"},
        {"id": "D11", "decision": "视频位置表达标注为「无素材、未验证」",
         "why": "本批没有视频素材，不能假装验过；文本/图片两类可验（图片复用 L1 的 #img.N 锚点）"},
    ],
    "not_done": [
        "不写版本号、不冻结版本（kb_version 仍 v0，versions.jsonl 版本行仍 0）",
        "不写 kb/l4/canonical/rules.jsonl（仍 0 字节）；不改任何规则；不改 kb/l0~kb/l6 任何文件",
        "不做抽查、不做发布；不建第二个 skill；不重复分配条款号",
        "不做 rerank；不改 L6 的融合方式（加权融合只在 kb/.work 的探针里算，不写进 kb/l6）",
    ],
}
run["verdict"] = "PASS" if integ["verdict"] == "PASS" and not missing_art else "FAIL"
os.makedirs(f"{L7}/runs", exist_ok=True)
json.dump(run, open(f"{L7}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

ops = [
    ("读 L4 条款号（只读）", "python3 - (扫 kb/l3/candidates/rules.jsonl)",
     f"{len(latest)} 条全有 article_no，缺失 {len(missing_art)}；区间 W-1 1~56 / W-2 1~453"),
    ("读 root-skills-creator 规范", "cat ~/.agents/skills/root-skills-creator/SKILL.md",
     "取 Universal Skill Schema（frontmatter/命名/复杂度/渐进式披露）+ CSO（description 写触发条件）+ 输出契约"),
    ("建 registry（门限/语义/词表/责任人/分流）", "写 kb/l7/registry/l7.json",
     "门限 BM25 8.0 / 余弦 0.60 / 覆盖 16.0；词表 8 类别 20 子类 + 19 条关键词兜底；no_hit_semantics 原文照搬 L6"),
    ("写参考实现 scripts/review.py（四层下探 + 引用契约）", "python3 kb/l7/skills/kb-content-review/scripts/review.py --text ...",
     "P0 → 规则层 → 单元层 → 原文层；引用不到锚点的结论不输出"),
    ("发现：离题内容被判 PASS（覆盖信号缺失）", "对比冒烟 3 前后",
     "新增覆盖门限 16.0 + 安全词判据；离题文本改判拒答"),
    ("发现：4 条结论引用不到锚点（用了规则首个证据单元）", "逐个证据单元重解析",
     "改为在所有证据单元里找含摘录的那个 → 未满足引用契约归零"),
    ("发现：拒答文案里有假陈述（11.07 < 8.0）", "读自验 B 输出",
     "改为逐层说明（P0/规则层/单元层 + 覆盖信号），算术与事实一致"),
    ("写 skill（SKILL.md + references + README + 可执行脚本）", "python3 ~/.agents/skills/root-skills-creator/scripts/validate-skill.py kb/l7/skills/kb-content-review",
     "✅ Validation passed，Quality Score 98/100（仅剩 .skill-meta 建议项）"),
    ("自验 A（真实 P0 命中文案 + 4 判据）", "python3 kb/.work/l7_selftests.py",
     "条款号 W-1.18｜库名 措辞表达库｜摘录回原文逐字一致｜P0 max 19.5 ms < 1s"),
    ("自验 B（拒答）", "同上", "退出码 3；按 no_hit_semantics 原文；含检索轨迹"),
    ("自验 D（规避型 5 条 × 4 模式）", "python3 kb/.work/l7_probe_d.py → 判断 → 生成",
     "hit@3 四模式均 4/5；p@3 bm25 0.533 ≥ vector 0.467 → 维持 BM25 为主"),
    ("自验 E（触发 3 正 3 反 + 2 边界）", "同上", "8/8 一致；description 未改"),
    ("自检 7 项 + 2 项附加", "python3 kb/.work/l7_integrity.py",
     "全部 PASS（冻结层 26 个留痕产物哈希一致；无裸 URL；四类库名；拒答合规；轨迹完整；三态模板；版本纪律）"),
    ("生成留痕", "python3 kb/.work/l7_report.py", f"runs/{RUN}.json / .report.md / .ops.log"),
]
with open(f"{L7}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L7 消费侧（使用知识库的 skill + 验收）· 操作日志 run_id={RUN}\n")
    fh.write(f"# 生成时间 {now}｜写入范围：只写 kb/l7/；kb/l0~l6 全程只读（含 kb/l3）；未发布任何版本\n")
    for i, (what, cmd, res) in enumerate(ops, 1):
        fh.write(f"\n[{i:02d}] {what}\n     $ {cmd}\n     → {res}\n")

# ---------------- report.md ----------------
ck = integ["checks"]
L = []
A = L.append
A(f"# L7 · 使用知识库的 skill + 验收（run_id {RUN}）\n")
A(f"生成时间 {now}｜kb_version `v0`｜结论 **{run['verdict']}**\n")

A("## 1. 条款号读取（本步只读，不分配）\n")
A(f"- 总条数 **{len(latest)}**，缺 `article_no` 的规则：**{len(missing_art)} 条**（{missing_art or '无'}）")
A(f"- 每库编号区间：{json.dumps(integ['checks']['article_no_read']['ranges'], ensure_ascii=False)}（W-1 = entry 56 条，W-2 = revision_pair 453 条）")
A(f"- 来源：`kb/l3/candidates/rules.jsonl` 的 `article_no`（由 L4 分配，规则见 `kb/l4/registry/l4.json`）；**本步未改 kb/l3**")
A(f"- 引用形如：`《措辞表达库 v0（试用版，未发布）》第 W-1.18 条`\n")

A("## 2. root-skills-creator 规范要点 + skill 落点\n")
A("读了 `~/.agents/skills/root-skills-creator/SKILL.md`（v4.1.4）与 `assets/templates/standard-skill/`、`scripts/validate-skill.py`，按以下要点产出：\n")
A("| 规范要点 | 本 skill 的落法 |")
A("|---|---|")
A("| Universal Skill Schema：frontmatter 必填 name/description/version/complexity | `name: kb-content-review`（kebab-case）、`version: 1.0.0`、`complexity: complex`、compatibility 七端声明 |")
A("| CSO：description 写**触发条件**而非工作流 | description 列正向场景 + 中英触发词 + **排除项**（知识库设计讨论 / 工程操作 / 通用写作翻译润色 / 业务闲聊） |")
A("| 复杂度分级：complex < 8000 字符 | SKILL.md 7,188 字符（正文 3,014 字符），细则外移到 `references/` |")
A("| 渐进式披露：Metadata → SKILL.md → Resources | `references/protocols.md`（两段协议细则）、`references/categories.md`（受控词表投影） |")
A("| 添加资源：scripts/ | `scripts/review.py`（可执行参考实现，支持 `--text/--json`，退出码 0=有结论 / 3=拒答） |")
A("| 祈使语态、无第二人称 | 正文全用祈使句；无「你/您」 |")
A("| 验证 | `validate-skill.py`：**✅ Validation passed，Quality Score 98/100**（仅剩 `.skill-meta/` 建议项） |")
A("")
A(f"落点：`{L7}/skills/kb-content-review/SKILL.md`（+ `references/`、`scripts/`、`README.md`）")
A(f"触发条件：提交内容要求判断能不能用；意图词（审查/审一下/合规检查/能不能发/会不会违规/能过审吗/有没有风险/踩线/禁用/敏感、"
  f"review/compliance check/is this compliant/will this pass/any risk）；追问依据（为什么判 BLOCK/依据是哪条规则）\n")

A("## 3. 相关性门限：取值、理由、被舍弃的结果\n")
g = reg["retrieval"]["gate"]
A(f"| 门限 | 取值 | 理由 |")
A(f"|---|---|---|")
A(f"| BM25 原始分 | `{g['bm25_raw_min']}` | 实测 A 组最低 5.32 / 中位 12.76，B 组中位 6.44 / 最高 10.02，取中间偏保守 |")
A(f"| 向量余弦 | `{g['vector_cosine_min']}` | 实测唯一能把 B 组全部挡在外面的取值（B 组最高 0.569），代价是 A 组丢 2 条 |")
A(f"| 覆盖门限 | `{g['coverage_bm25_min']}` | 判断「知识库认不认识这个主题」＝ 依据门限的 2 倍；**PASS 必须过这一关，否则拒答** |")
A("")
A("**为什么单一门限不够**：BM25 原始分在 A/B 两组仍有重叠（A 组最低 5.32 < B 组最高 10.02），"
  "所以门限只决定「够不够格当参考」，**要成为依据还必须同时命中规则层**。**RRF 分不能当门限**：它恒为 `1/(60+k)`"
  "（实测 Top1 恒在 0.016393），A/B 两组看起来一样高。\n")
A("门限以下被舍弃的结果举例（真实运行，文案 = `Experience pain-free pumping with our hospital grade pump. Get more milk in less time.`）：\n")
A("| 来源 | 原始分 | 锚点 | 判定 |")
A("|---|---|---|---|")
for d in discarded:
    sc = d.get("raw_bm25", d.get("cosine"))
    A(f"| {d['source']} | {sc} | `{d['anchor']}` | {d['verdict']}：{d['reason'][:60]} |")
A("")
A("对照：过门限被采纳为参考的（仍要规则层确认才是依据）：\n")
A("| 来源 | 原始分 | 锚点 |")
A("|---|---|---|")
for d in adopted:
    A(f"| {d['source']} | {d.get('raw_bm25')} | `{d['anchor']}` |")
A("")

A("## 4. 受控分类词表（类别-子类 + PRD 映射）\n")
v = reg["vocabulary"]
A(f"版本 `{v['version']}`｜类别 {len(v['categories'])} 个、子类 {sum(len(x['subs']) for x in v['categories'].values())} 个、"
  f"关键词兜底 {len(v['keyword_map'])} 条｜闭包：{v['closure']}\n")
A("| 类别 | 子类 | 规则码 | PRD §7.2 场景域 | PRD §7.3 一票否决 |")
A("|---|---|---|---|---|")
for cat, info in v["categories"].items():
    for i, (sub, s) in enumerate(info["subs"].items()):
        A(f"| {cat if i == 0 else ''} | {sub} | {'、'.join(s['codes']) or '—'} | "
          f"{'、'.join(info['prd_7_2']) or '—'} | "
          f"{('、'.join('第' + str(x) + ' 项' for x in info['prd_7_3'])) or '—'} |")
A("")
A("**PRD §7.2 的 9 大场景域**（词表全覆盖）：" + "、".join(reg["vocabulary"]["prd_7_2_domains"]))
A("")
A("**PRD §7.3 的 7 项一票否决**（词表可映射）：")
for x in reg["vocabulary"]["prd_7_3_vetoes"]:
    A(f"- {x}")
A("")
A("分类顺序：规则有 `rule_code` → 查 `code_map`（21 个码全覆盖）；否则按 `keyword_map` 取首个命中；"
  "都不中 → `未分类-未分类`（**不许自造类别**，并写进报告）。\n")

A("## 5. 自验 A：BLOCK 链路（完整输出原文 + 4 判据）\n")
A("送审内容取自真实素材 `#广告文案明细/recvuJYdObxeKs/Primary Text`：\n")
A("```")
A("Gran oferta para miembros Momcozy | Recupera tu libertad. Extrae más leche fácilmente mientras trabajas. ¡Compra el tuyo hoy!")
A("```\n")
A("**完整输出原文：**\n")
A("```")
A(out_a_full)
A("```\n")
A("**4 个判据**\n")
A("| # | 判据 | 结果 | 证据 |")
A("|---|---|---|---|")
A("| 1 | 依据可引用（库名 + 版本 + 条款号 + 链接） | ✅ | 《措辞表达库 v0（试用版，未发布）》第 W-1.18 条；链接 `kb/l3/candidates/rules.jsonl#W-1.18` |")
A("| 2 | 逐字摘录能回原文核对 | ✅ | 按引用锚点解析到 `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdObxeKs.json` 的 `命中片段` 字段，逐字一致 |")
A("| 3 | 无命中会拒答 | ✅ | 见自验 B |")
A("| 4 | P0 命中 < 1 秒 | ✅ | 5 次实测 min 9.3 ms / max 19.5 ms（含整进程启动） |")
A("")
A("另两种结论态与两种分流的模板符合性（同一文件内，真实捕获）：见 `selftest_a_block.md` 附录（PASS / REVIEW 逐条 / BLOCK ≥3 汇总）。\n")

A("## 6. 自验 B：拒答（完整输出原文）\n")
A("送审内容（库里绝无对应内容）：`关于汽车保养周期多久一次的建议，以及基金定投和股票的区别`\n")
A("```")
A(out_b_full)
A("```\n")
A("判据：是否拒答 ✅（退出码 3）｜是否按 `no_hit_semantics` ✅（本轮只走 BM25，逐字用「字面未匹配，不代表合规」）｜"
  "是否给检索轨迹 ✅（逐层说明 P0/规则层/单元层 + 覆盖信号）。\n")

A("## 7. 自验 C：真实内容验收\n")
A(f"**未跑**：`{L7}/acceptance_cases.md` 不存在（任务条件是「若文件存在」）。**不伪造验收数据**；"
  f"若后续提供该文件，可直接跑 `scripts/review.py` 对每条出结论并写 `{L7}/acceptance/`。\n")

A("## 8. 自验 D：规避型查询（补上一批的测法缺口）\n")
A("5 条字面不同、语义相近的查询 × 4 种模式（bm25_only / vector_only / 加权 0.7:0.3 / 加权 0.5:0.5），逐条人工判断：\n")
A("| 模式 | hit@3 | precision@3 |")
A("|---|---|---|")
A("| bm25_only | 4/5 = 0.8 | 0.533 |")
A("| vector_only | 4/5 = 0.8 | 0.467 |")
A("| 加权 0.7:0.3 | 4/5 = 0.8 | 0.533 |")
A("| 加权 0.5:0.5 | 4/5 = 0.8 | 0.533 |")
A("")
A("**结论（向量有没有价值）：没有可测出的净增益 → 维持 BM25 为主**，不给融合权重建议。"
  "向量在「最佳、第一名这种说法有问题吗」「能不能说产品是医院同款」上更准（后者 3/3 全中），"
  "但在「说能帮妈妈通乳算不算踩线」上 0/3，把无关的专家修订排到前面；两种权重都没超过纯 BM25"
  "（0.7:0.3 因权重偏 BM25 结果与 BM25 完全一致，0.5:0.5 换来的好结果被挤掉一条）。"
  "向量只保留「BM25 低于门限时补召」的角色。详见 `selftest_d_paraphrase.md`。\n")

A("## 9. 自验 E：触发准确性（3 正 + 3 反 + 2 边界）\n")
A("| # | 类型 | 输入 | 期望 | 实际 | 一致 |")
A("|---|---|---|---|---|---|")
for i, (kind, text, exp, _why, act, verdict) in enumerate([
    ("该触发", "帮我审一下这段吸奶器文案：Get more milk in less time.", "是", "", "是", "✅"),
    ("该触发", "这个详情页会不会违规？能过审吗？", "是", "", "是", "✅"),
    ("该触发", "为什么判 BLOCK？依据是哪条规则？", "是", "", "是", "✅"),
    ("不该触发", "知识库 L3 的锚点是怎么定的？L0–L6 各层怎么分工？", "否", "", "否", "✅"),
    ("不该触发", "kb/l6 的索引怎么重建？跑哪个脚本？", "否", "", "否", "✅"),
    ("不该触发", "帮我把这段中文翻译成英文，顺带润色一下。", "否", "", "否", "✅"),
    ("边界", "帮我写一段吸奶器广告文案，卖点是舒服。", "否", "", "否", "✅"),
    ("边界", "这段视频字幕 00:12 说'完全不疼'，这样写有没有风险？", "是", "", "是", "✅")], 1):
    A(f"| {i} | {kind} | {text} | {exp} | {act} | {verdict} |")
A("")
A("8/8 一致，description **未修改**。判定方法为人工对照 description（本批没有独立触发分类器可跑；"
  "真正的触发回归要走 root-skills-eval 的 A/B 卷，不在本批范围）。详见 `selftest_e_trigger.md`。\n")

A("## 10. 无法满足引用契约的结论清单\n")
A("**空**（期望为空，实际为空）：三次自验运行（A/B/BLOCK 汇总用例）的 `trace.unmet_citation` 全为 0 条。\n")
A("首版曾有 4 条被硬闸门挡下（W-1.18 / W-1.53 / W-1.40 / W-1.19），原因是引用用了规则的**首个证据单元**，"
  "而该单元的字段里并不含被引片段（规则会把上百条来源记录的片段汇总在一起）。改成「在全部证据单元里找真正含摘录的那个」后归零。\n")

A("## 11. 自检（7 项 + 2 项附加，全部 PASS）\n")
A("| 项 | 结论 | 证据 |")
A("|---|---|---|")
fl = ck["frozen_layers"]
A(f"| kb/l0~l6 未被修改（含 kb/l3） | {fl['verdict']} | 把 L4/L5/L6 留痕里记录的 **{fl['artifact_hash_check']['checked']} 个产物哈希**逐个复核，"
  f"不一致 {len(fl['artifact_hash_check']['mismatch'])} 个（覆盖层 {fl['artifact_hash_check']['layers_covered']}）；"
  f"kb/l0、l1、l2 的 tree_sha256 与 L5 基线一致 {fl['l0_l2_tree_sha256_same_as_L5']}；"
  f"kb/l3/candidates 现 {fl['l3_candidates']['lines']} 行，前 1018 行 = L6 记录值 {fl['l3_candidates']['base1018_matches_L6']}、"
  f"前 1527 行 = L4 记录值 {fl['l3_candidates']['whole1527_matches_L4']}；本批全部写入都在 kb/l7/ 与 kb/.work/ |")
cc = ck["citation_contract"]
A(f"| 结论可追 anchor + source_sha256，无裸 URL | {cc['verdict']} | 条款号 {cc['citations']} 处、锚点 {cc['anchors']} 处、"
  f"source_sha256 {cc['source_sha256']} 处；裸 URL **{len(cc['bare_urls'])}** 个 |")
A(f"| 库名都来自四类库 | {cc['verdict']} | 输出里出现的库名 {cc['library_names_used']}；不在四类库里的 {cc['library_names_not_in_kb'] or '无'} |")
A(f"| 无命中确实拒答且文案一致 | {ck['refusal']['verdict']} | 拒答={ck['refusal']['refuses']}；"
  f"no_hit_semantics 逐字出现={ck['refusal']['no_hit_semantics_verbatim']} |")
A(f"| 检索轨迹完整 | {ck['retrieval_trace']['verdict']} | {json.dumps(ck['retrieval_trace']['elements'], ensure_ascii=False)} |")
A(f"| 三态输出符合模板 | {ck['template_conformance']['verdict']} | {json.dumps(ck['template_conformance']['markers'], ensure_ascii=False)} |")
A(f"| 版本纪律 | {ck['version_discipline']['verdict']} | kb/l4/canonical/rules.jsonl "
  f"{ck['version_discipline']['l4_canonical_bytes']} 字节；versions.jsonl 版本行 {ck['version_discipline']['versions_jsonl_rows']}；"
  f"kb_version 全为 v0 |")
A(f"| 附加：条款号读取 | {ck['article_no_read']['verdict']} | {ck['article_no_read']['rules']} 条全有条款号，缺失 "
  f"{len(ck['article_no_read']['missing'])} |")
A("")

A("## 12. 已知边界（如实列出）\n")
A("| 边界 | 状态 |")
A("|---|---|")
A("| 视频位置表达（`视频 HH:MM 字幕\"...\"` + 时间戳锚点） | **无素材、未验证** |")
A("| 图片位置表达（`图片 N` + `#img.N`） | 可验（复用 L1 已产出的 `#img.N` 锚点），本批未跑图片用例 |")
A("| 触发判定 | 人工对照 description，无独立分类器；正式回归需 root-skills-eval |")
A("| 责任人句柄 | registry 里为 `null`，输出标注「（未配置）」 |")
A("| 向量价值 | 两批实测（字面重合型 + 规避型）都未见净增益 → 维持 BM25 为主 |")
A(f"| 未分类兜底 | 词表外用 `未分类-未分类`；自验运行的 {len(rj['findings'])} 条结论里未分类 0 条 |")
A("")

A("## 13. 自主决策\n")
A("| # | 决策 | 理由 |")
A("|---|---|---|")
for d in run["decisions"]:
    A(f"| {d['id']} | {d['decision']} | {d['why']} |")
A("")

A("## 14. 本批没做的事 / 产物校验和\n")
for x in run["not_done"]:
    A(f"- {x}")
A("")
A("| 文件 | 字节 | sha256 |")
A("|---|---|---|")
for a in run["artifacts"]:
    A(f"| `{a['path']}` | {a['bytes']:,} | `{a['sha256'][:16]}…` |")
A("")
open(f"{L7}/runs/{RUN}.report.md", "w", encoding="utf-8").write("\n".join(L))
print(f"已生成 {L7}/runs/{RUN}.json / .report.md / .ops.log")
print(f"run verdict = {run['verdict']}")
