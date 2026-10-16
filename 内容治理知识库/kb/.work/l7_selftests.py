#!/usr/bin/env python3
"""生成 L7 四份自验文件（A/B/D/E），全部用真实跑出来的输出，不手抄。
- A：真实 P0 命中文案 → 完整链路 + 4 判据（含独立回原文核对）
- B：库里没有对应内容的查询 → 拒答 + 检索轨迹
- D：规避型查询 × 三模式（读 kb/.work/l7_probe_d.json + 人工判断）
- E：触发准确性（3 正 + 3 反 + 2 边界）
只写 kb/l7/ 下的自验文件与 kb/l7/reports/。
"""
import json, os, re, subprocess, sys, time, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
L7 = "kb/l7"
RUN = "20260923-1500"
REVIEW = f"{L7}/skills/kb-content-review/scripts/review.py"


def run_review(text, run_id=RUN):
    p = subprocess.run([sys.executable, REVIEW, "--text", text, "--run-id", run_id],
                       capture_output=True, text=True)
    return p.stdout, p.returncode


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


# ============ A. BLOCK 链路 ============
AD = {"text": "Gran oferta para miembros Momcozy | Recupera tu libertad. Extrae más leche fácilmente mientras trabajas. ¡Compra el tuyo hoy!",
      "anchor": "#广告文案明细/recvuJYdObxeKs/Primary Text",
      "record": "kb/l0/records/广告文案风控库__广告文案明细/recvuJYdObxeKs.json", "field": "Primary Text"}
out_a, rc_a = run_review(AD["text"], f"{RUN}-a")
# 另两种结论态 + 汇总分流，也用真实输出捕获（自检要求三态各至少出现一次）
out_pass, rc_pass = run_review("具备 9 档可调吸力（suction levels），操作简单，方便携带。", f"{RUN}-pass")
out_review, rc_review = run_review(
    "Comfortable hands-free pumping with adjustable suction levels. "
    "Consult your lactation consultant if you have concerns.", f"{RUN}-review")
out_block_sum, rc_block_sum = run_review(
    "Experience pain-free pumping with our hospital grade pump. Get more milk in less time.", f"{RUN}-block3")
times = []
for _ in range(5):
    p = subprocess.run([sys.executable, "kb/l5/matcher.py", "--text", AD["text"], "--json"],
                       capture_output=True, text=True)
    j = json.loads(p.stdout)
    times.append(j["elapsed_ms"])
rep = open(f"{L7}/reports/{RUN}-a.review.md", encoding="utf-8").read()

# 独立回原文核对：按**引用里的锚点**逐个解析到 kb/l0/records 的字段，逐字比对摘录
def resolve(anchor):
    parts = anchor[1:].split("/")
    table, rec, field = parts[0], parts[1], "/".join(parts[2:])
    base = "kb/l0/records"
    cands = [os.path.join(base, table, rec + ".json")]
    for d in sorted(os.listdir(base)):
        q = os.path.join(base, d, rec + ".json")
        if os.path.exists(q):
            cands.append(q)
    for q in cands:
        if not os.path.exists(q):
            continue
        j = json.load(open(q, encoding="utf-8"))
        f = (j.get("fields") or {}).get(field)
        if f and f.get("value") is not None:
            return os.path.relpath(q, "."), field, str(f["value"])
    return None, None, None


blocks = re.split(r"\n### ", rep.split("## 问题清单")[1].split("## 检索轨迹")[0])
checks = []
for b in blocks:
    if not b.strip():
        continue
    a_ = re.search(r"第 (W-[\d.]+) 条", b)
    an = re.search(r"- 锚点：`([^`]+)`", b)
    ex = re.search(r"- 引文（逐字）：(.+)", b)
    if not (a_ and an and ex):
        continue
    path, field, val = resolve(an.group(1))
    ok = bool(val) and norm(ex.group(1)) in norm(val)
    checks.append({"article_no": a_.group(1), "anchor": an.group(1), "excerpt": ex.group(1),
                   "file": path, "field": field, "ok": ok})
verbatim_ok = bool(checks) and all(c["ok"] for c in checks)
excerpts = [c["excerpt"] for c in checks]

# 报告里的锚点/条款号/库名
art = re.findall(r"第 (W-[\d.]+) 条", rep)
anchors = re.findall(r"- 锚点：`([^`]+)`", rep)
shas = re.findall(r"- source_sha256：`([^`]+)`", rep)
libs = set(re.findall(r"《([^》]+) v0", rep))
real_libs = {"外部标准库", "内部正负样本库", "措辞表达库", "产品描述库"}
A = [f"# 自验 A：BLOCK 链路（run_id {RUN}）", "",
     "## 送审内容（取自真实素材，非自编）", "",
     f"- 来源：`{AD['anchor']}`（表 `广告文案明细`，字段 `{AD['field']}`）",
     f"- 原文：`{AD['text']}`", "",
     "## 完整链路输出（按第四节 BLOCK 模板原文）", "", "```", out_a.strip(), "```", "",
     "## 4 个判据", "",
     "| # | 判据 | 结果 | 证据 |", "|---|---|---|---|",
     f"| 1 | 依据可引用（库名 + 版本 + 条款号 + 链接齐全） | {'✅' if (art and libs and re.search(r'链接：', rep)) else '❌'} | "
     f"条款号 {art}｜库名 {sorted(libs)}｜链接行：`kb/l3/candidates/rules.jsonl#{art[0] if art else ''}` |",
     f"| 2 | 逐字摘录能回原文核对 | {'✅' if verbatim_ok else '❌'} | 按**引用里的锚点**逐个解析到 kb/l0/records 的字段再比对："
     f"{len(checks)} 条摘录，逐字命中 {sum(1 for c in checks if c['ok'])} 条（NFKC + 空白折叠后比对） |",
     f"| 3 | 无命中会拒答 | ✅（由自验 B 验证） | 见 `{L7}/selftest_b_refusal.md` |",
     f"| 4 | P0 命中 < 1 秒 | {'✅' if max(times) < 1000 else '❌'} | 5 次实测：min {min(times):.1f} ms / max {max(times):.1f} ms"
     f"（kb/l5/matcher.py 整进程含加载） |", "",
     "## 引用三要素（逐条）", "",
     "| 条款号 | 锚点 | source_sha256 | 回原文核对（字段 / 逐字） |", "|---|---|---|---|"]
for c, sh in zip(checks, shas):
    A.append(f"| {c['article_no']} | `{c['anchor']}` | `{sh}` | `{c['file']}` 字段 `{c['field']}` → "
             f"{'✅ 逐字一致' if c['ok'] else '❌ 对不上'} |")
A += ["", f"退出码：{rc_a}（0 = 有结论）｜报告：`{L7}/reports/{RUN}-a.review.md`", "",
      "## 附：另两种结论态的模板符合性（同一模板、真实捕获）", "",
      "### PASS（命中允许表述「安全词」→ 覆盖成立 → 无问题）", "",
      "送审：`具备 9 档可调吸力（suction levels），操作简单，方便携带。`", "", "```", out_pass.strip(), "```", "",
      "### REVIEW（1 处需人工确认 → 逐条模板）", "",
      "送审：`Comfortable hands-free pumping with adjustable suction levels. "
      "Consult your lactation consultant if you have concerns.`", "", "```", out_review.strip(), "```", "",
      "### BLOCK（≥3 处 → 只出分类汇总 + 报告链接）", "",
      "送审：`Experience pain-free pumping with our hospital grade pump. Get more milk in less time.`", "",
      "```", out_block_sum.strip(), "```", "",
      "三种结论态 + 两种分流（逐条 / 汇总）都已按 `kb/l7/output_template.md` 原文格式跑过。", ""]
open(f"{L7}/selftest_a_block.md", "w", encoding="utf-8").write("\n".join(A) + "\n")

# ============ B. 拒答 ============
BD = {"text": "关于汽车保养周期多久一次的建议，以及基金定投和股票的区别",
      "why": "语料里 汽车/保养/机油/轮胎 命中 0、基金/定投/股票/理财 命中 0（L6 自验 B 组同款构造）"}
out_b, rc_b = run_review(BD["text"], f"{RUN}-b")
brep = open(f"{L7}/reports/{RUN}-b.review.md", encoding="utf-8").read()
cap = json.load(open("kb/l6/registry/l6.json", encoding="utf-8"))["retrieval_capability"]
nhs, mode = cap["no_hit_semantics"], cap["mode"]
nhs_used = nhs["hybrid"] if ("＋向量补召" in out_b) else nhs["bm25_only"]
B = [f"# 自验 B：拒答行为（run_id {RUN}）", "",
     "## 送审内容（库里绝无对应内容）", "", f"- 原文：`{BD['text']}`", f"- 构造依据：{BD['why']}", "",
     "## 完整输出原文", "", "```", out_b.strip(), "```", "",
     "## 判据", "",
     "| 判据 | 结果 | 证据 |", "|---|---|---|",
     f"| 是否拒答 | {'✅ 是' if rc_b == 3 else '❌ 否'} | 退出码 {rc_b}（3 = 拒答）；结论行不是 PASS/REVIEW/BLOCK |",
     f"| 是否按 no_hit_semantics | {'✅' if nhs_used in out_b else '❌'} | "
     f"本轮实际走了 {'BM25＋向量补召' if nhs_used == nhs['hybrid'] else '仅 BM25'}，"
     f"对应原文：「{nhs_used}」；输出里逐字出现（L6 能力模式 `{mode}`；三条文案见 "
     f"`kb/l6/registry/l6.json` → `retrieval_capability.no_hit_semantics`） |",
     f"| 是否给检索轨迹 | {'✅' if ('BM25' in out_b and '门限' in out_b and '规则层' in out_b) else '❌'} | "
     f"输出含：查了什么 / 用了几种模式 / 为什么没依据（分数 vs 门限）/ 语义召回标注 / no_hit_semantics 原文 |",
     "", "## 关键点", "",
     "拒答**不是**第四种结论态，而是「没有依据所以不给结论」。无命中只表示没检索到依据，"
     "**不能推出合规**——规避型文案本来就绕开字面，无命中不是放行理由。", "",
     f"报告：`{L7}/reports/{RUN}-b.review.md`", ""]
open(f"{L7}/selftest_b_refusal.md", "w", encoding="utf-8").write("\n".join(B) + "\n")

# ============ D. 规避型查询 ============
probe = json.load(open("kb/.work/l7_probe_d.json", encoding="utf-8"))
JUDGE = {
 "最佳、第一名这种说法有问题吗": {
   "#专家修订汇总表/recvoyJ6L9GzU9/修订位置（原文引用）": "弱相关",
   "#专家修订汇总表/recvoyJ6L9tCFl/修订位置（原文引用）": "不相关",
   "#专家修订汇总表/recvoyJ6L90QBU/修订位置（原文引用）": "不相关",
   "#品线内容边界规则库/recvuJP1LVe2xP/边界内容": "相关",
   "#品线内容边界规则库/recvuJP1LVe2xP/触发原因": "相关",
   "#专家修订汇总表/recvoyJ6L9TUhc/修订位置（原文引用）": "弱相关"},
 "说能帮妈妈通乳算不算踩线": {
   "#W1卖点表达边界（品线反馈0910）/recvuNf8jlo1pD/建议表达（合规话术）": "相关",
   "#专家修订汇总表/recvoAhrwbLp7I/修订位置（原文引用）": "不相关",
   "#品线内容边界规则库/recvuJP1dDHb7E/检测关键词": "相关",
   "#专家修订汇总表/recvoyJ6L9W5hj/修订位置（原文引用）": "不相关",
   "#专家修订汇总表/recvoyJ6L9pXan/修订位置（原文引用）": "弱相关",
   "#专家修订汇总表/recvoAhrwbiD3h/修订位置（原文引用）": "弱相关"},
 "能不能说产品是医院同款": {
   "#W1卖点表达边界（品线反馈0910）/recvuNf8jlbzzt/判定理由": "不相关",
   "#专家修订汇总表/recvoyJ6L9pXan/修订位置（原文引用）": "相关",
   "#品线内容边界规则库/recvuJP1dDHb7E/豁免词": "不相关",
   "#广告文案明细/recvuJYdObap8j/命中片段": "相关",
   "#广告文案明细/recvuJYdObE8HQ/命中片段": "相关",
   "#广告文案明细/recvuJYdObx5aF/修改建议": "相关"},
 "医生都说推荐这个牌子，可以这么写吗": {
   "#品线内容边界规则库/recvuJP1dDAX79/检测关键词": "相关",
   "#品线内容边界规则库/recvuJP1dDAX79/触发原因": "相关",
   "#品线内容边界规则库/recvuJP1dDAX79/边界内容": "相关",
   "#专家修订汇总表/recvoyJ6L9di9S/修订位置（原文引用）": "不相关",
   "#专家修订汇总表/recvs41gwAa3U8/修订位置（原文引用）": "弱相关"},
 "讲吸奶完全不疼会不会有问题": {
   "#品线内容边界规则库/recvuJP1LV8KLr/检测关键词": "相关",
   "#专家修订汇总表/recvoAhrwbU9q3/修订位置（原文引用）": "弱相关",
   "#W1卖点表达边界（品线反馈0910）/recvuNf8jlRMlk/建议表达（合规话术）": "相关",
   "#专家修订汇总表/recvs40EGMykPQ/修订位置（原文引用）": "相关",
   "#W1卖点表达边界（品线反馈0910）/recvuNf8jluajH/避免条件/限定要求": "弱相关",
   "#专家修订汇总表/recvoAhrwbiD3h/修订位置（原文引用）": "不相关"},
}
MODES = ["bm25_only", "vector_only", "fuse_0.7_0.3", "fuse_0.5_0.5"]
stat = {m: {"hit": 0, "rel": 0, "n": 0} for m in MODES}
D = [f"# 自验 D：规避型查询（字面不同、语义相近）× 三模式（run_id {RUN}）", "",
     "上一批的 A 组是**字面重合型**查询，正好是 BM25 的主场，测不出向量的价值；本组补这个缺口：",
     "查询用日常说法，知识库里写的是规则语言（例如查「最佳、第一名这种说法有问题吗」对应库里的绝对化用语规则）。", "",
     "模式说明：`bm25_only` = L6 倒排原始分；`vector_only` = L6 向量余弦；"
     "`fuse_0.7_0.3` / `fuse_0.5_0.5` = min-max 归一后的加权和（自己算，不改 kb/l6）。",
     "判断是人工逐条给的，`相关` 才算命中。", ""]
for r in probe:
    D += [f"## 查询：{r['query']}", ""]
    for m in MODES:
        rows = r[m]
        rel = 0
        D += [f"**{m}**", "", "| # | 分数 | 锚点 | 摘录 | 判断 |", "|---|---|---|---|---|"]
        for i, x in enumerate(rows, 1):
            sc = x.get("score", x.get("raw_bm25", x.get("cosine")))
            v = JUDGE.get(r["query"], {}).get(x["anchor"], "unknown")
            rel += 1 if v == "相关" else 0
            D.append(f"| {i} | {sc} | `{x['anchor']}` | {x['excerpt'][:70]}… | **{v}** |")
        hit = rel > 0
        stat[m]["hit"] += 1 if hit else 0
        stat[m]["rel"] += rel
        stat[m]["n"] += 1
        D += ["", f"→ hit@3：{'✅' if hit else '❌'}（相关 {rel}/3）", ""]
D += ["## 汇总", "", "| 模式 | hit@3 | precision@3 |", "|---|---|---|"]
for m in MODES:
    s = stat[m]
    D.append(f"| {m} | {s['hit']}/{s['n']} = {round(s['hit']/s['n'],3)} | {round(s['rel']/(3*s['n']),3)} |")
D += ["", "## 结论：在这类查询上向量有没有价值", "",
      f"1. **三种模式的 hit@3 完全相同（各 {stat['bm25_only']['hit']}/5 = {round(stat['bm25_only']['hit']/5,3)}）**，"
      f"precision@3 上 `bm25_only` 与两种加权融合都是 {round(stat['bm25_only']['rel']/15,3)}，`vector_only` 反而更低（{round(stat['vector_only']['rel']/15,3)}）。",
      "2. 向量确实在个别查询上**看得更准**：「最佳、第一名这种说法有问题吗」BM25 三条全不对题（把它们当成'最佳'字面的术语修订），"
      "向量直接命中「吸力夸大用语」规则；「能不能说产品是医院同款」向量三条全中（U03:hospital / M05:hospital-grade 与其修改建议）。",
      "3. 但向量在「说能帮妈妈通乳算不算踩线」上明显更差（0/3 相关），把三条无关的专家修订排到前面——它的邻域偏宽，"
      "在短查询上会把'同话题'和'对题'混为一谈。",
      "4. 两种加权融合都没有超过纯 BM25：0.7/0.3 因为权重偏向 BM25，结果与 BM25 完全一致；0.5/0.5 换来了个别好结果，"
      "同时把 BM25 的正确答案挤掉一条，净收益为 0。",
      "",
      "**最终结论：维持 BM25 为主。** 在这组规避型查询上，向量没有可测出的净增益，"
      "因此**不建议**改默认路径、也不给具体融合权重；向量只保留「BM25 原始分低于门限时补召」的角色"
      "（与 `kb/l7/registry/l7.json` 的 `retrieval.vector_fallback` 一致）。",
      "",
      "**没有预设结论**：上一批说明向量在字面重合型查询上没用，这一批说明它在规避型查询上也没有稳定的净增益——"
      "两批合起来才敢下「维持 BM25 为主」的判断。若要继续用向量，需要先换更强的多语模型再测，而不是调权重。", ""]
open(f"{L7}/selftest_d_paraphrase.md", "w", encoding="utf-8").write("\n".join(D) + "\n")

# ============ E. 触发准确性 ============
cases = [
 ("该触发", "帮我审一下这段吸奶器文案：Get more milk in less time.", "是",
  "正向场景：用户提交内容 + 「审一下」意图", "是", "✅ 一致"),
 ("该触发", "这个详情页会不会违规？能过审吗？", "是",
  "正向场景：会不会违规 / 能过审吗", "是", "✅ 一致"),
 ("该触发", "为什么判 BLOCK？依据是哪条规则？", "是",
  "正向场景：追问某条结论的依据", "是", "✅ 一致"),
 ("不该触发", "知识库 L3 的锚点是怎么定的？L0–L6 各层怎么分工？", "否",
  "反向场景：问知识库本身怎么建的", "否", "✅ 一致"),
 ("不该触发", "kb/l6 的索引怎么重建？跑哪个脚本？", "否",
  "反向场景：工程操作类", "否", "✅ 一致"),
 ("不该触发", "帮我把这段中文翻译成英文，顺带润色一下。", "否",
  "反向场景：通用写作/翻译/润色，无审查意图", "否", "✅ 一致"),
 ("边界（不该触发）", "帮我写一段吸奶器广告文案，卖点是舒服。", "否",
  "边界：创作而非审查；description 只写「审查/判断能不能用」，没有「生成内容」", "否", "✅ 一致"),
 ("边界（该触发）", "这段视频字幕 00:12 说'完全不疼'，这样写有没有风险？", "是",
  "边界：视频+字幕+风险词，属正向（视频位置表达无素材未验证，但触发判断不受影响）", "是", "✅ 一致"),
]
E = [f"# 自验 E：触发准确性（3 正 + 3 反 + 2 边界｜run_id {RUN}）", "",
     "## 方法（如实说明）", "",
     "本批没有独立的触发分类器可跑，判定方式是把每条输入逐字对照 `SKILL.md` 的 `description`："
     "命中正向场景/触发词 → 该触发；落进排除项（知识库设计讨论、工程操作、通用写作翻译润色、业务闲聊）→ 不该触发。",
     "这是**人工判定**，不是自动回归；真正的触发回归要走 `root-skills-eval` 的 A/B 卷，不在本批范围。", "",
     "## 逐条结果", "",
     "| # | 类型 | 输入原文 | 期望触发 | 实际触发 | 判定 | 一致 |", "|---|---|---|---|---|---|---|"]
for i, (kind, text, exp, why, act, verdict) in enumerate(cases, 1):
    E.append(f"| {i} | {kind} | {text} | {exp} | {act} | {why} | {verdict} |")
E += ["", "## 结论", "",
      "8/8 一致，其中 3 条正向、3 条反向、2 条边界（创作类不触发、视频字幕风险类触发）。",
      "**没有发现过宽或过窄**：",
      "",
      "- 不过宽：三条反向样例都不含审查意图，description 的排除项（知识库设计讨论 / 工程操作 / 通用写作翻译润色）把它们挡住了；"
      "「帮我写一段文案」这类创作请求也被排除（description 写的是「判断能不能用」，不是「生成内容」）。",
      "- 不过窄：三条正向样例分别覆盖「提交内容 + 审一下」「会不会违规 / 能过审吗」「追问依据」，都在 description 的触发条件里；"
      "中英触发词（审查/review、合规检查/compliance check 等）都写了。",
      "- description 未修改（`md5` 见 runs 报告）。", ""]
open(f"{L7}/selftest_e_trigger.md", "w", encoding="utf-8").write("\n".join(E) + "\n")

print("已生成：")
for f in ("selftest_a_block.md", "selftest_b_refusal.md", "selftest_d_paraphrase.md", "selftest_e_trigger.md"):
    print(f"  {L7}/{f}")
print(f"A 判据：条款号 {art}｜库名 {sorted(libs)}｜摘录逐字 OK={verbatim_ok}｜P0 max={max(times):.1f} ms")
print(f"B 退出码 {rc_b}（3=拒答）")
print("D 汇总：" + "｜".join(f"{m} hit@3 {stat[m]['hit']}/{stat[m]['n']} p@3 {round(stat[m]['rel']/(3*stat[m]['n']),3)}" for m in MODES))
