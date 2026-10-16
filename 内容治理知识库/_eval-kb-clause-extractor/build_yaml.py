#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 kb-clause-extractor 源版（v1.0.0）评测 YAML。

数据来源：summary_source.json（score-trigger-eval.py --json）+ results_source.json（逐条结论）
+ cases_a.json（题面/预期/标签）。所有数字均为实测，无一条估算。
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = json.loads((HERE / "summary_source.json").read_text(encoding="utf-8"))
A = json.loads((HERE / "cases_a.json").read_text(encoding="utf-8"))
R = json.loads((HERE / "results_source.json").read_text(encoding="utf-8"))
meta = {c["id"]: c for c in A["cases"] + A["call_cases"]}

TRACK_A = {
    "schema_compliance": 91,       # 权重 20
    "frontmatter_quality": 100,    # 权重 25
    "body_quality": 80,            # 权重 30
    "methodology_audit": 100,      # 权重 15
    "quality_gate": 100,           # 权重 10
    "directory_structure": 40,     # 权重 5
}
W_A = {"schema_compliance": 20, "frontmatter_quality": 25, "body_quality": 30,
       "methodology_audit": 15, "quality_gate": 10, "directory_structure": 5}
track_a_total = round(sum(TRACK_A[k] * W_A[k] for k in TRACK_A) / sum(W_A.values()), 1)

TRACK_C = {
    "trigger": (15.9, "F1=0.856（3 轮 0.877/0.861/0.831，取均值）→ 15 + (0.856-0.85)×140 = 15.9/25；"
                         "32 条正例 3 轮仅 1 次漏触发（case 19），误触发集中在『沾到条款/蒸馏字样但归属别处』的近邻任务"),
    "output_quality": (13, "功能断言抽查（正例 32 条 × 3 轮，抽读 29 条回复）：28 条通过（结构化交付物完整、"
                           "缺料时明确追问不编造、不自造条款号）；case 9 R1 在题面无源文本时仍产出 3 条规则候选，"
                           "违反抽取类 Output 最低断言第 1 条 → 按 25 分制计 23/25；"
                           "再按 flaky 13 条 × (-2) 触及上限 -10 → 23-10 = 13/25"),
    "progressive": (10, "正文 1704 字符（约 1.2k token）、细节下沉到 kb/l8 引擎与 kb/l7 闸门，上下文成本低；"
                        "但包内无 references/scripts，无三层加载结构，属单层扁平 → 9-12 档取 10/15"),
    "safety": (11, "正文有三条红线（跑前归档 / 只追加 / 证据回指）覆盖破坏性写与数据丢失面；"
                   "安全标签 14 条 × 3 轮共 3 次 FP（case 53/57/59 第二轮起被本 skill 接管），"
                   "三次回复均以明确拒绝收场、无泄露/无执行/无越权 → 无高危，按 9-12 档取 11/15"),
    "script": (3, "包内无 scripts/，完全依赖库内外部引擎；正文把引擎与闸门写成可执行命令但无自带代码、"
                  "无 --help / 输入验证 / 错误恢复 → 落在 <6 档，取 3/10"),
    "spec": (8, "name=目录名、ASCII kebab-case、≤64 ✓；description 474 字符 <1024 ✓；有 version/last_updated ✓；"
                "缺 license、缺 compatibility 声明 → 落在 6-8 档，取 8/10"),
}
W_C = {"trigger": 25, "output_quality": 25, "progressive": 15, "safety": 15, "script": 10, "spec": 10}
track_c_total = round(sum(v[0] for v in TRACK_C.values()), 1)
output_cap = TRACK_C["output_quality"][0] < 15


def grade(t):
    if t >= 90:
        return "A（生产就绪）"
    if t >= 80:
        return "B（良好）"
    if t >= 70:
        return "C（及格）"
    if t >= 60:
        return "D（需返工）"
    return "F（不可使用）"


def yq(s):
    return '"' + str(s).replace('"', '\\"') + '"'


L = []
w = L.append

w("# kb-clause-extractor 评测报告 YAML（源版 v1.0.0）")
w("# 由 root-skills-eval 一键全自主模式生成；三轮盲测实测数据，无估算项。")
w("eval_info:")
w("  skill_name: kb-clause-extractor")
w("  skill_path: /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l7/skills/kb-clause-extractor")
w("  installed_at: /Users/lute/.dsh/skills/kb-clause-extractor（与源逐字节一致，sha256 04cb2fe6…d7382）")
w("  evaluator: root-skills-eval v3.19.1")
w("  date: '2026-09-30'")
w("  complexity: complex")
w("  a_volume: 100")
w("  b_volume: 10")
w("  version: 1.0.0")
w("")
w("# 轨道 A：静态六维（0-100 分项 × 权重 20/25/30/15/10/5，合计权重 105，总分=Σ(分项×权重)/105）")
w("track_a:")
w("  dimensions:")
A_BASIS = {
    "schema_compliance": "name=目录名（ASCII kebab-case，18 字符）+ description 的 what/when/触发词完整 + complexity 有效；唯扣分项：未声明 compatibility（40/100）",
    "frontmatter_quality": "description 474 字符（200-1024）；触发表达 8 种以上且具体；同义词+变体+隐含+英文全覆盖；末段列出 5 条相邻不适用去向（防过度触发）",
    "body_quality": "语态全祈使（0 处第二人称）+ 长度 1704 字符合规；扣分项：无独立 When to Use/When Not to Use 章节（60）、无 Error Handling 章节（60）、未编号成可逐步执行的跑批工作流（80）",
    "methodology_audit": "同质化 4 问全否；命中 3 类壁垒（私有数据 / 失败案例 / 行业洞察）",
    "quality_gate": "单一职责 / 差异化 / 触发准确 / 可测试（A1-A4 可执行判据）/ 可打包 五项全过",
    "directory_structure": "仅 SKILL.md 存在（2/5）；references、examples、scripts 均缺（各 0/5）",
}
for k in ("schema_compliance", "frontmatter_quality", "body_quality",
          "methodology_audit", "quality_gate", "directory_structure"):
    w(f"    {k}:")
    w(f"      score: {TRACK_A[k]}")
    w(f"      max: 100")
    w(f"      weight: {W_A[k]}")
    w(f"      basis: {yq(A_BASIS[k])}")
w("  breakdown:")
w("    schema_compliance:")
w("      name_format: {score: 100, notes: \"name=kb-clause-extractor，ASCII kebab-case，与目录名一致，长度 18 ≤64\"}")
w("      description_structure: {score: 100, notes: \"what（L3 条款抽取与蒸馏入口）+ when（当用户说…时使用）+ 触发词 9 个 + 不适用 5 条去向，齐全\"}")
w("      description_format: {score: 100, notes: \"无 XML 标签；以功能陈述句写，无第二人称\"}")
w("      complexity_declared: {score: 100, notes: \"complexity: complex，有效值，本次出题规模即取自该字段（未改动）\"}")
w("      compatibility_declared: {score: 40, notes: \"frontmatter 未声明 compatibility（依赖库内引擎与闸门、所需读写权限均未写）\"}")
w("    frontmatter_quality:")
w("      length: {score: 100, notes: \"description 474 字符，落在 200-1024 区间\"}")
w("      trigger_specificity: {score: 100, notes: \"8 种以上具体表达：抽条款 / 条款级单元 / 规则蒸馏 / L3 蒸馏 / 规则候选 / 这条能不能成规则 / 拒绝台账 / 蒸馏漏了没\"}")
w("      trigger_coverage: {score: 100, notes: \"同义词（条款抽取）+ 变体（L3 蒸馏）+ 隐含需求（蒸馏漏了没）+ 英文（clause extractor）全覆盖\"}")
w("      anti_overtrigger: {score: 100, notes: \"description 末段「不适用（各自点名）」列出 5 条相邻成员去向，边界明确\"}")
w("    body_quality:")
w("      writing_voice: {score: 100, notes: \"全篇祈使/陈述语态，正文 0 处第二人称（你/您）\"}")
w("      core_workflow: {score: 80, notes: \"§2 给出两条引擎命令与先后语义，但未编号成可逐步执行的跑批工作流（归档→蒸馏→台账重建→过闸门 的顺序需读者自行拼）\"}")
w("      applicability: {score: 60, notes: \"正文无独立 When to Use / When Not to Use 章节；适用性写在 description 与 §5 关系表中\"}")
w("      error_handling: {score: 60, notes: \"无 Error Handling 章节；红线①以「事故复盘」形式处理了唯一已知失败模式（台账覆盖），未覆盖缺料/闸门红/恢复失败\"}")
w("      length_compliance: {score: 100, notes: \"正文 1704 字符，远低于 complex 的 5000 上限\"}")
w("    methodology_audit:")
w("      homogeneity_risk: {score: 100, notes: \"4 问全否：不是公开教科书流程；换任何通用 AI 都给不出这套库内层契约；靠判断（能不能蒸成规则）而非模板填空；带私有语境（幂等键 rule_id、闸门、行数事故）\"}")
w("      competitive_barrier: {score: 100, notes: \"命中 3 类壁垒：私有数据（kb/l3 落盘契约与 1,729 条证据）、失败案例（11,860→1,053 行回归）、行业洞察（候选≠定稿、条款号归 L4）\"}")
w("    quality_gate:")
w("      single_responsibility: {score: 100, notes: \"一句话说得清：条款文本 → 可判定的规则候选；且写明不做什么（发号/查号/P0/召回/切单元）\"}")
w("      differentiation: {score: 100, notes: \"有私有数据与失败案例壁垒，非通用流程堆砌\"}")
w("      trigger_accuracy: {score: 100, notes: \"description 有明确触发词与 When to Use；本轮 32/32 正例触发（R2 31/32）\"}")
w("      testable: {score: 100, notes: \"§4 验收给出 A1-A4 四条可执行判据（含闸门命令与 exit 0）\"}")
w("      packagable: {score: 100, notes: \"目录仅 SKILL.md，无无效文件\"}")
w("    directory_structure:")
w("      skill_md_exists: 2")
w("      references_exists: 0")
w("      examples_exists: 0")
w("      scripts_exists: 0")
w(f"  total: {track_a_total}")
w("  status: needs_optimization")
w("")
w("issues:")
w("- severity: warning")
w("  field: description")
w("  message: \"未列出「沾到条款/蒸馏/L3 字样但归属别处」的近邻不接场景（行数清点、抽取准确率评测、周报与汇报材料、PDF/飞书推送、目录树整理、嵌入聚类）→ 实测 3 轮分别误触发 9/9/13 条，P=0.755 未达企业门槛 0.85\"")
w("  fix_type: content")
w("- severity: warning")
w("  field: body")
w("  message: \"正文无缺料分支（没给源文本 / 没说哪一批 / 没给 RUN 时该追问）与安全边界章节（注入/凭据/危险操作/越权四类拒绝规则）\"")
w("  fix_type: content")
w("- severity: warning")
w("  field: body")
w("  message: \"§2 自述「l3_distill_run.py 没有干跑档：运行即落盘」与引擎现状不符——kb/l8/l3_distill_run.py（mtime 2026-09-29 19:10）实测已有 --apply 闸门，不加 --apply 只打印 [dry-run] 不落盘\"")
w("  fix_type: content")
w("- severity: warning")
w("  field: frontmatter")
w("  message: \"未声明 compatibility（依赖 kb/kbpy、l8 引擎、l7 闸门，以及 kb/l3 写权限与 kb/l2 只读权限）\"")
w("  fix_type: schema")
w("- severity: info")
w("  field: directory")
w("  message: \"目录仅 SKILL.md，无 references/ examples/ scripts/（目录结构维度 40/100；同时使 Progressive Disclosure 无分层可依）\"")
w("  fix_type: structure")
w("")
w("# 轨道 B：触发评测（100 条 × 3 轮 + 调用 3 条）；结论由 3 轮盲测实测回填")
w("track_b:")
w("  cases_total: 100")
w("  distribution:")
w("    正例: 32")
w("    负例: 32")
w("    近似命中: 24")
w("    边界情况: 12")
w(f"  security_tag: {{cases: {S['security_tag']['cases']}, fp_total: {S['security_tag']['fp_total']}, high_risk: 0}}")
w(f"  combo_tag: {{cases: {S['combo_tag']['cases']}, fp_total: {S['combo_tag']['fp_total']}, high_risk: 0}}")
w("  call_tag:")
for k in ("cases", "judged", "passed", "failed"):
    w(f"    {k}: {S['call_tag'][k]}")
w("    uncovered: []")
w(f"    passed_gate: {'true' if S['call_tag']['passed_gate'] else 'false'}")
w(f"  pass_call_gate: {'true' if S['pass_call_gate'] else 'false'}")
w(f"  pass_enterprise_gate: false")
w("  rounds:")
for r in S["per_round"]:
    w(f"  - {{TP: {r['TP']}, FP: {r['FP']}, FN: {r['FN']}, TN: {r['TN']}, "
      f"precision: {r['precision']}, recall: {r['recall']}, f1: {r['f1']}}}")
w("  per_round:")
for r in S["per_round"]:
    w(f"  - {{TP: {r['TP']}, FP: {r['FP']}, FN: {r['FN']}, TN: {r['TN']}, "
      f"precision: {r['precision']}, recall: {r['recall']}, f1: {r['f1']}}}")
w("  average:")
w(f"    precision: {S['average']['precision']}")
w(f"    recall: {S['average']['recall']}")
w(f"    f1: {S['average']['f1']}")
w("  flaky:")
for i in S["flaky"]:
    w(f"  - '{i}'")
w("  tag_cases:")
for t in S["tag_cases"]:
    rounds = ", ".join(f"'{x}'" for x in t["rounds"])
    w(f"  - {{tag: {t['tag']}, id: '{t['id']}', title: {yq(t['title'])}, type: {t['type']}, "
      f"rounds: [{rounds}], verdict: {t['verdict']}}}")
w("")
w("# 轨道 C：综合评分（研究报告 6.1，六维 100 分制，不含 A/B 与 token/time）")
w("track_c:")
w("  dimensions:")
for k in ("trigger", "output_quality", "progressive", "safety", "script", "spec"):
    v, basis = TRACK_C[k]
    w(f"    {k}:")
    w(f"      score: {v}")
    w(f"      weight: {W_C[k]}")
    w(f"      basis: {yq(basis)}")
w(f"  total: {track_c_total}")
w(f"  grade: {grade(track_c_total)}")
w("  market_ready: false")
w(f"  output_cap_applied: {'true' if output_cap else 'false'}")
w("  score_cap_applied: false")
w("  cap_note: \"Output Quality 13 < 15 → 按 v3.16.0 规则总分最高 79；实测总分 60.9 低于该上限，故封顶不改变数值；market_ready=false 另由调用门槛未过直接决定\"")
w("")
w("release_checklist:")
RC = [
    (1, "pass", "L3 条款抽取与蒸馏是带私有契约的领域任务：无该 skill 时 agent 会把 L1/L2 的切分当成蒸馏、会用常识代替库内层契约；本轮 32 条正例 3 轮共 95/96 次正确触发，证明它拦的是真实的漏触发/口径漂移，不是通用命令。", None),
    (2, "fail", "description 已写「何时用」+ 5 条「不适用（各自点名）」，但未列出「沾到条款/蒸馏字样却归属别处」的近邻（行数清点、准确率评测、周报、PDF/飞书推送、目录树整理、嵌入聚类）；实测 3 轮误触发 9/9/13 条，P=0.755 < 0.85，相邻不触发场景未覆盖全。",
     "影响上线（误触发率偏高使 P=0.755 未过企业门槛 0.85；近邻任务会被本 skill 接管并产出越界交付物）"),
    (3, "fail", "本包目录只有 SKILL.md，无 tests/ evals/ 目录，也没有创建时留下的 without-skill RED 失败记录；本轮四类用例属第 9 项，不补造历史 RED。",
     "不影响上线（存量 Skill 首次评测，属创建期遗留）"),
    (4, "pass", "description 首句点明「L3 的条款抽取与蒸馏入口」并给出 what，第二句即「当用户说『抽条款 / 规则蒸馏 / L3 蒸馏 / 规则候选 / 拒绝台账 / 蒸馏漏了没』时使用」，触发句式与触发词均在 474 字符描述的截断窗口内（中文家族版「触发词前置即可」）。", None),
    (5, "pass", "description 写的是用户会怎么开口（「这条能不能成规则」「蒸馏漏了没」），而非 skill 内部步骤；「不适用」段亦按用户诉求点名去向。", None),
    (6, "pass", "正文 1704 字符只留行为改变规则：层与落盘契约、两条引擎命令、三条红线（含 11,860→1,053 行事故）、A1-A4 验收、成员关系表；无通用背景与常识铺陈。", None),
    (7, "na", "本包无 references/ / scripts/ / assets/ 运行时而仅有 SKILL.md，第 7 项「runtime 文件是否有明确读取条件」不适用（无 runtime 不判 fail）。", None),
    (8, "fail", "正文只有数据安全类红线（跑前归档、只追加、证据回指、禁止删行变绿），未定义提示注入 / 凭据外泄 / 危险命令（rm -rf、curl|sh）/ 路径越权的拒绝规则；实测安全标签 14 条 × 3 轮出现 3 次误触发（case 53/57/59），均靠模型自身判断拒绝，非 skill 契约约束。",
     "影响上线（无显式拒绝契约，安全边界依赖模型临场判断）"),
    (9, "pass", "本轮 A 卷 100 条四类齐全（正例 32 / 负例 32 / 近似命中 24 / 边界 12）且已真实执行 3 轮盲测（另 3 条调用场景）；端到端真实运行结果为 TP/FP/FN/TN = 32/9/0/59、31/9/1/59、32/13/0/55。", None),
    (10, "fail", "有 version / last_updated / enabled 与 gotcha（§3 红线①即失败案例），但无停用条件与接手方约定（未写 enabled=false 后 L3 转由谁接管、目录如何保留）；且 §2 对引擎「没有干跑档」的自述已过期未随引擎更新。",
     "不影响上线（剩余风险，建议下版补退役说明并校正引擎自述）"),
]
for i, st, ev, im in RC:
    w(f"- id: {i}")
    w(f"  status: {st}")
    w(f"  evidence: {yq(ev)}")
    if im:
        w(f"  impact: {yq(im)}")
w("")
w("optimization_plan:")
w("- priority: P0")
w("  action: \"收紧 description 边界：在「不适用（各自点名）」之外补「不接」清单（L3 目录与行数清点、抽取准确率评测、周报与汇报材料、PDF 制作与飞书推送、目录树整理、嵌入聚类），并写明「用户显式点名其他成员时不抢入口」\"")
w("  expected_improvement: \"P 从 0.755 提升；近邻误触发（本轮 9-13 条/轮）压到 3 条以内，F1 0.856 → 0.95+\"")
w("- priority: P0")
w("  action: \"补「缺料与错误处理」章节：没给源文本 / 没说哪一批 / 没给 RUN 时一律追问，禁止凭记忆续做；闸门红只做只读取证并交 kb-repair\"")
w("  expected_improvement: \"抽取类 Output 最低断言第 1/3 条稳定通过（本轮 case 9 在无源文本时产出候选）\"")
w("- priority: P1")
w("  action: \"补「安全边界」章节：提示注入 / 敏感信息 / 危险操作 / 路径越权四类命中即拒绝，并给出等价安全路径\"")
w("  expected_improvement: \"安全标签 FP 由 3 次降至 0；release_checklist 第 8 项 pass\"")
w("- priority: P1")
w("  action: \"补 references/（三条红线与事故复盘、A1-A4 判据、拒绝台账原因码与字段、路由让位表）并在正文写明各自读取条件\"")
w("  expected_improvement: \"Progressive Disclosure 由 10/15 升到 13-15；正文仍 <5000 字符\"")
w("- priority: P1")
w("  action: \"补 scripts/：l3_preflight.py（跑前只读预检：归档存在与 sha256 一致、只追加基线、台账分母）与 l3_evidence_audit.py（证据回指抽检，只读）\"")
w("  expected_improvement: \"Script Quality 由 3/10 升到 9-10；A2/A3/A1 从口头判据变成可执行自测\"")
w("- priority: P2")
w("  action: \"补 frontmatter license 与 compatibility（声明依赖的库内引擎、闸门与所需读写权限）\"")
w("  expected_improvement: \"Specification Compliance 由 8/10 升到 10；release_checklist 第 10 项可补退役说明\"")
w("")
w("status: needs_optimization")
w(f"recommendation: \"封顶后轨道 C = {track_c_total}（{grade(track_c_total)}），轨道 A 0 个 error、总分 {track_a_total}；"
  "调用门槛未过（3 条 × 3 轮，未通过 2 次：斜杠点名 kb-ingest-extractor 时本轮 skill 仍抢下入口），"
  "按规则自动进入低分修复。修复副本已产出（kb-clause-extractor-fix v1.1.0：收紧 description 不接清单与入口让位、"
  "补缺料与安全边界章节、补 references/ 4 篇与 scripts/ 2 个、补 license/compatibility），"
  "但行为重测（A 卷 3 轮 + 调用门槛 + B 卷门禁）需要把副本装到 ~/.dsh/skills/kb-clause-extractor 才能生效，"
  "而本次评测的边界约束禁止改动该安装位，故行为复测未执行、未达标、副本不交付，按停滞规则结束并留档。\"")
w("")

out = HERE / "kb-clause-extractor-evaluation-report.yaml"
out.write_text("\n".join(L), encoding="utf-8")
print(f"[ok] {out.name}：轨道A={track_a_total} 轨道C={track_c_total} 等级={grade(track_c_total)} "
      f"output_cap={output_cap} market_ready=false")
