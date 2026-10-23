#!/usr/bin/env python3
"""第 5 步：P0 可执行导出 —— 规则 → 机器可执行的匹配表。
kb/l0~l2 只读；kb/l3 只追加；产物写 kb/l5。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import json, os, re, hashlib, collections, sys, unicodedata

# ── 批次14 · 0-2：把 `kb/` 放进 sys.path，使 `import kb_ledger` 可用 ─────────────
# 首版兜底实测踩到：`No module named 'kb_ledger'`（本脚本原先不需要库路径）。
# 兜底必须真的生效 —— 否则它会静默退化成「只用手上字段」，然后写出 0 条 P0
# （实测把 p0_patterns.jsonl 从 7 条写成 0 条，已从 pre-edit 备份还原）。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# ── 干跑档 · 开关解析（P0-3 · 2026-09-29 补）───────────────────────────────
# 必须早于 RUN 解析：把 --apply 从 argv 里剔除，避免它被当成位置参数 run_id。
APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
# ──────────────────────────────────────────────────────────────────────────

# ── 干跑档 · 落盘闸门（P0-3b · 2026-09-29 前移到「第一个副作用之前」）──────
# 位次判据：闸门必须早于本脚本的**第一个副作用**（建目录 / 下载 / 写缓存 / 写库内文件）。
# 原 P0-3 位次在副作用之后 → 干跑并不零写；且紧跟闸门之后的写语句会因
# 「纯注释行不产生 DEDENT」被词法器吞进闸门体 —— 编译照样通过，--apply 时却永不执行
# （报告成功、实际丢写入）。故整体前移。
if not APPLY:
    print("[dry-run] %s 未落盘。" % _os.path.basename(_os.path.abspath(__file__)))
    print("[dry-run] 本脚本会写入：L5 出表：覆盖写 kb/l5/p0_patterns.jsonl、l5/index/l5.jsonl、l5/registry/l5.json")
    print("[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）")
    _sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────
RUN = sys.argv[1]
L0, L2, L3, L5 = "kb/l0", "kb/l2", "kb/l3", "kb/l5"
EXPORTER_VERSION = "l5-0.1"
KB_VERSION = "v0"
for d in ("index", "registry", "runs"):
    os.makedirs(f"{L5}/{d}", exist_ok=True)

# ---------- 规则（生行 + 富化，**唯一实现**）
# ★ 2026-10-10（方案 A）：原先这里有一份**私有的**富化兜底（批次14 0-2 加的）。
#   它与 `l5_prep.py` / `l5_report.py` / `l5_gate.py` 里各自的实现是**同一件事的四份拷贝** ——
#   实测代价：同一条坑（候选层只有生行）在这个月里栽了三次，每次只修当时崩的那一处。
#   现在收成一个口：`kb/kb_ledger.py::rules_enriched_view`（含 `evidence_digest` 校验，
#   旧拷贝都**没验 digest** ⇒ 上游改过正文后会照旧套用旧富化、分类静默错）。
#   口径**一字未改**：只补缺失的键、不覆盖已有值；富化唯一真源 = `manifest_l3`。
import kb_ledger as _kl
# ★ 2026-10-13：规则来源**两个候选件**合成一个视图。
#   为什么必须合：`candidates/rules.jsonl` 是**措辞库**的候选件（1018 行全 `kb_type=wording`），
#   把外部标准规则塞进去会让 `l7_gate` 的 C2「现行规则库名（1）」判不出唯一库名（实测红）。
#   而外部标准规则本来就有自己的候选件 `candidates/external_standard.jsonl`（既有 123 条）。
#   ⇒ 各归其位，在**读侧**合成 —— 不合并文件（文件契约各自不变）。
# ★ 2026-10-13 稍后：合成**收成一个口**（`kb_ledger.rules_enriched_view_multi`）。
#   原先只在本文件内联合成，`l5_report.py` 没跟上而崩 —— 病灶见该函数 docstring。
#   `_RID_SRC` 由「只登记外部标准」变成「全量登记」：调用处是
#   `_RID_SRC.get(rid, "rules")`，两条路的取值**逐条不变**。
_RULE_SRC = {"rules": f"{L3}/candidates/rules.jsonl",
             "external_standard": f"{L3}/candidates/external_standard.jsonl"}
latest, _enrich_stats, _RID_SRC = _kl.rules_enriched_view_multi(
    _RULE_SRC, f"{L3}/manifest_l3.jsonl")
print(f"[来源] 措辞候选 + 外部标准候选合成视图 → 共 {len(latest)} 个 rule_id")
_kl.assert_no_stale_enrichment(_enrich_stats, "l5_export")
print(f"[富化] 生行 {_enrich_stats['read']} 行 / {_enrich_stats['uniq']} 个 rule_id ｜ "
      f"从 manifest_l3 补齐 {_enrich_stats['backfilled']} 条 ｜ "
      f"无富化 {_enrich_stats['no_enrich']} ｜ 陈旧 {_enrich_stats['stale']}")

# ---------- 变体扩展表
# 约束：变体必须落在规则已给出的表述范围内（forbidden_expression / suggested_replacement /
# rule_text 里出现过的词），或由「同一语义族的等价说法」保守派生；不得引入源里没有的新事实。
VARIANTS = {
    'V01': {   # 儿童乘车安全（PRD §7.3 一票否决项）
        "literal": ["未使用安全座椅", "反向安装错误", "成人未系安全带", "安全座椅装副驾", "儿童独留车内"],
        "synonym": ["没坐安全座椅", "未坐安全座椅", "没有安全座椅", "坐在成人腿上", "坐在大人腿上", "独自留在车内", "单独留在车内", "未系安全带", "没系安全带"],
        "regex": [],
    },
    'V02': {   # 绝对化用语（PRD §7.3 一票否决项）
        "literal": ["绝对化用语", "纯天然", "最佳"],
        # ★★ 2026-10-14：**「最好」一度摘掉、当天已回退** —— 见上面 H05 正则那段取证。
        #   受控实验证明摘掉它会让「最好的吸奶器」从 BLOCK 变 **PASS**（L3 不认这个词）。
        #   顺带记一条**真缺陷**（与本次裁定无关，但该修）：V02 的 7 个词里
        #   `最佳/纯天然/100%/第一/最安全` **全部已被 H05 的正则覆盖** ⇒ V02 是**冗余模式**，
        #   它唯一多出来的检出就是「最好」。要不要给 V02 收窄/并档，等法务与 Owner 定。
        "synonym": ["100%", "第一", "最好", "最安全"],
        "regex": [],
        # ★★ 2026-10-19（Owner 裁定 A，逐字）：「美国市场是可以超级、最好这些夸张词的 ⇒ 这类词不再判断为问题」。
        #   本轮**只出列主观最高级**，不是整族放开：
        #     · 出列：`最佳`（VARIANTS literal ＋ 源侧 forbidden_expression 里也有）、`最好`（synonym）。
        #     · 留下：`纯天然`（成分事实宣称，可验证）、`100%`（绝对化量化宣称）、
        #             `最安全`（安全承诺，婴儿用品高风险）、`第一`（排名宣称，需依据；V03 也管这一族）。
        #   ⚠️ 出列走导出处的 `exclude` 机制（唯一实现）。只从这里删词**无效** ——
        #      `最佳` 还来自 src_frags（源侧 forbidden_expression），导出时会被补回来。
        "exclude": ["最佳", "最好"],
    },
    'V03': {   # 无依据的销量/排名宣称（PRD §7.3 一票否决项）
        "literal": ["无依据的销量/排名宣称", "排名宣称"],
        "synonym": ["销量第一", "销量领先", "排名第一"],
        "regex": [],
    },
    'V04': {   # 危险行为示范（PRD §7.3 一票否决项）
        "literal": ["危险行为示范", "无人看护下水", "趴睡", "怀抱乘车"],
        "synonym": ["驾驶时怀抱", "无人看护"],
        "regex": [],
    },
    'V05': {   # 未成年人出镜/隐私暴露（PRD §7.3 一票否决项）
        "literal": ["未成年人未经授权出镜", "隐私暴露"],
        "synonym": ["儿童出镜", "孩子出镜"],
        "regex": [],
    },
    'V06': {   # AI 深度合成内容未标识（PRD §7.3 一票否决项）
        "literal": ["AI 深度合成内容未标识"],
        "synonym": ["未标注AI", "AI生成未标注"],
        "regex": [],
    },
    "H07": {   # 疼痛功效承诺
        "literal": ["pain-free", "painless", "painlessly", "no pain", "zero pain",
                    "indolore", "sans douleur", "schmerzfrei", "sin dolor",
                    "say goodbye to cold, painful"],
        "synonym": ["without pain", "pain relief", "relieve pain", "free of pain",
                    "无痛", "缓解疼痛", "不痛", "告别疼痛"],
        "regex": [r"(no|without|free\s+of|zero)\s+(more\s+)?pain\b",
                  r"\bpain[\s-]*(free|less)\b",
                  r"无\s*痛|缓解\s*疼痛|不\s*会\s*痛"],
    },
    "H02": {   # 催乳/奶量产出承诺
        "literal": ["more milk", "increase milk supply", "increasing milk supply",
                    "increases milk production", "boost supply", "triggers letdown",
                    "easier let-down", "easier letdown", "faster let-down",
                    "improve pumping efficiency", "augmente la production de lait",
                    "mehr milch", "más leche", "plus de lait", "producción de leche"],
        "synonym": ["boost milk", "increase milk", "milk supply boost", "maximize milk",
                    "增产", "催奶", "催乳", "下奶", "奶量提升", "增加奶量"],
        "regex": [
            # ★★ 2026-10-12 补：**物主代词只认 `your` 的缺口**。
            #   改前逐字：`\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+(your\s+)?milk\b`
            #   ⇒ `her / his / my / their / our / its` **一律断掉**。
            #   实证（`kb/l5/matcher.py --text … --json`）：
            #     `it actually increased her milk supply` → **MISS**
            #     `it increased my milk supply`            → **MISS**
            #     对照 `… increased your milk supply`      → **HIT H02**（同一句话换个人称就不拦）
            #   为什么不是边角：**达人脚本与 UGC 叙事恰恰用第一/第三人称**
            #     （"she said…" / "I've noticed…"），而那正是要审的素材类型。
            #     回归集 100 条里就有 1 条踩中（`RC-b2390ccfe4f8`，逐字含
            #     `it actually increased her milk supply`）—— 它现在**被覆盖缺口兜住**
            #     （零命中、`issue_count=0` ⇒ 转人工），**不是因为被识别**；
            #     **一旦该题材被库覆盖，它就会变成 PASS** ⇒ 真漏放会显形。
            #
            #   ★ 为什么不放 `the`（我原来的推荐里写了它，落地时去掉）：
            #     `the` **不是人称**，放进去会把「increases the milk supply」这类**科普句**
            #     也拦下 —— 那不是本次要修的缺口，属另一次扩面，得单独裁。
            #   ★ 误报面（改前实测，**放宽不引入新的误报"类"**）：
            #     `How do I increase your milk supply` ⇒ **今天就已命中 H02**
            #     ⇒ 疑问句形态**本来就在拦**，放宽只是把同一个类扩到别的人称。
            #     裸 `increased milk supply` / `more milk` 同样早就命中。
            #   ★ 反向对照（改后必须仍成立）：否定句不许被放宽带进去 ——
            #     `it did not increase her milk supply` 必须**仍 MISS**（whitelist 否定守卫管着）。
            #   回退：把本行换回上面那条 `(your\s+)?`，重跑 `--apply`（旧表留档见
            #     `kb/l5/runs/<RUN>.p0_patterns.superseded.jsonl`）。
            r"\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+"
            r"((?:your|her|his|my|their|our|its)\s+)?milk\b",
            r"\blet[\s-]?down\b",
            r"增\s*产|催\s*奶|催\s*乳|下\s*奶"],
    },
    "H04": {   # 无据的医生/专家推荐背书
        "literal": ["ibclc-recommended", "recommended by 100+ experts", "ob-gyn recommended"],
        "synonym": ["doctor recommended", "doctor-recommended", "expert recommended",
                    "expert-recommended", "expert-tuned", "pediatrician recommended",
                    "医生推荐", "专家推荐", "专家调校", "专家认证推荐"],
        "regex": [r"\b(doctor|physician|pediatrician|expert|ibclc|ob[\s-]?gyn)[\s-]*"
                  r"(recommended|approved|endorsed|backed)\b",
                  r"医生\s*推荐|专家\s*推荐|专家\s*调校"],
    },
    "H05": {   # 虚假安全承诺 / 绝对化适配承诺
        "literal": ["perfect pump"],
        "synonym": ["safest", "100% safe", "100%safe", "zero risk", "risk-free",
                    "fits all breast shapes", "one size fits all",
                    "一定不损伤", "适合所有胸型", "完全安全", "零风险", "绝对安全"],
        "regex": [r"\b(safest|perfect|zero[\s-]?risk|risk[\s-]?free)\b",
                  r"\b100\s*%\s*(safe|safety)\b",
                  r"one[\s-]size[\s-]fits[\s-]all",
                  r"适合\s*所有\s*胸型|完全\s*安全|零\s*风险|绝对\s*安全|一定\s*不\s*损伤",
                  # ↓↓↓ 2026-10-09 按 PRD §7.3 第 3 条「绝对化用语（最、第一、最佳、100%、纯天然等）」补「最高级排名」子集。
                  # 当日实测：PRD 例词的 7 种中文写法（最安全/最好的/第一品牌/排名第一/最佳选择/100% 安全/纯天然）此前命中 0。
                  # 走 regex 不走 synonym：synonym 会被当「关键词命中片段」要求逐字可引用（见 H06 的教训），
                  # 这些词不在源里，塞进 synonym 会造出「P0 命中却 PASS」。
                  # 「最」「第一」「100%」一律带搭配限定，避免误伤 最近/最多/第一天/100% cotton 这类非绝对化用法。
                  # ★★ 2026-10-14（Owner 裁定「按你的推荐做」）：**`好` 出列**。
                  #   口径来自本规则自己的 `reason` 逐字：「best/#1/No.1/**最佳/最好**等排名最高级
                  #   按 2026-09-09 口径**放开**，海外广告允许，**不再判险**」——
                  #   放开的是**排名最高级**这一子类，而正则却把它一起收着 ⇒ **说明与判据打架**。
                  #   为什么只摘 `好`、不摘整族：跨过这条线就不再是「放开排名最高级」，
                  #   而是把「最安全/最强/最优/最有效/最舒适…」一整族也放开 —— 那**超出了**该口径。
                  #   `最佳`（另起一条独立的 `r"最佳"`）**本次未动**：它同属「排名最高级」，
                  #   但摘它属另一刀，且与 `reason` 同批的那次改动绑在一起 ⇒ 留给法务逐条确认。
                  #   ⚠️ 若将来要恢复：把 `好|` 加回下面这一行，重跑
                  #   `kb/.work/l5_export.py --apply`（旧表留档见 `kb/l5/runs/*.p0_patterns.superseded.jsonl`）。
                  # ★★ 2026-10-19（Owner 裁定 A）：**主观最高级整族出列** —— `最佳/最优/最强/最舒适` 摘掉。
                  #   口径：美国市场 puffery，不可验证的主观夸张不判问题（`super strong`/`the best`/`最强`）。
                  #   留下的都**可验证**：`最安全`（安全承诺）、`最有效/最快/最大/最高/最省`（效果与性能可测）、
                  #   `最低价/最便宜`（价格可核）—— 这三类在 FTC 下照样要 substantiation。
                  r"最\s*(安全|低价|便宜|有效|快|大|高|省)",
                  r"(排名|销量|全网|行业|品类|国内|全球|世界|亚洲)\s*第一",
                  r"第一\s*(品牌|选择|名|款|位)",
                  r"纯\s*天然",
                  r"100\s*%\s*(安全|有效|无痛|无副作用|纯|天然|放心|保障|满意)",
                  r"(?:\bno\.?\s*1|#\s*1)\b",   #  在 # 前不成立，故 #1 分支不带前置边界
                  # ★★ 2026-10-19：`\bbest\b` 出列（主观最高级）。
                  #   `best-selling` **仍然会拦** —— 走的是 M03（需依据的销量宣称），不是这里；
                  #   `#1 / No.1` 也**保留**（可验证的排名宣称，需依据），见上面那一条。
                  ],
    },
    "H03": {   # 未经备案的临床/科学背书（PRD #L478「功效宣称」→ 一票否决域）
        # 零新增词：禁用写法逐字存在于该规则 forbidden_expression
        # （源：品线内容边界规则库 recvuJP1dD4jGX，严格限制红线/高危），src_frags 自动取到。
        # ★ 2026-10-21：**规则自己的边界表述**另外登记在 `BOUNDARY_TERMS`（见上方常量），
        #   不走本表 —— 本表的纪律是「只列源侧命中片段」，边界表述不是命中片段。
        "literal": [], "synonym": [],
    },
    "H08": {   # 无数据支撑的违法对比 / 贬低竞品（PRD #L478「广告用语」→ 一票否决域）
        # 零新增词：同上（源：recvuJP1LVUEBx，严格限制红线/高危）。
        "literal": [], "synonym": [],
    },
    "H01": {   # 医疗功效声明（PRD §7.3 第 2 条「医疗功效宣称（治疗、预防疾病等）」，2026-10-09 Owner 裁定按 PRD 判）
        # ★ 本条**零新增词**：72 个禁用写法（含中文 33）已逐字存在于该规则的 forbidden_expression
        #   （源：L0「广告文案风控库/品线内容边界规则库」recvuJP1dDHb7E，边界类型=严格限制红线、风险等级=高危），
        #   下面的 src_frags 切分会自动取到 —— 重复列一遍会让溯源混成两处，反而更差。
        #   故意**不写 regex/synonym**：不引入源里没有的写法（本文件的变体表纪律）。
        "literal": [],
        "synonym": [],
    },
    "M03": {   # 无依据的销量/排名宣称（PRD §7.3 第 4 条，2026-10-09 Owner 裁定「按照 prd 升 P0」）
        # ★ 本条**零新增词**：禁用写法（bestseller / best-selling / hotseller / top rated /
        #   top-rated / trusted by 6 million / trusted by 6m 等）逐字存在于该规则
        #   forbidden_expression，下面的 src_frags 切分会自动取到。
        # ★ M03 有两个 rule_id，本次只升了 **r-4f309d6ebde80283**（锚点
        #   #广告文案明细/recvuJYdOb02Rt/命中片段）：它 authority=expert、rule_kind=atomic，
        #   **本来就过 `_sel_base` 门槛** ⇒ 不需要进 P0_CODE_ALLOWLIST（不是放宽门槛）。
        #   另一条 r-d00103c52a98512e（锚点 #品线内容边界规则库/recvuJP2jyATC9/边界内容，
        #   authority=inferred）**仍是 P1，未动** —— 它的检测关键词里有「吸力提升/效率提升/快一倍/
        #   多30%」这类效果描述，把它一起拉进「命中即 BLOCK」的误伤面太大；且两条同为 atomic，
        #   若都升 P0 会撞同一 rule_code ⇒ 触发上面的唯一性断言。要一并收它的词表，等 Owner 单独裁。
        # ★ 回溯：manifest_l3 里该 rule_id 的 p_level 由 P1 改 P0（备份 kb/l3/_backups/pre-m03-p0-20261009/）。
        #   回退 = 把那一行 p_level 改回 P1，并重跑 l5_export.py --apply。
        "literal": [],
        "synonym": [],
    },
    "H09": {   # 拟真吸吮/模仿婴儿
        "literal": ["mimics baby", "mimics baby’s natural nursing"],
        "synonym": ["mimic baby", "mimics a baby", "imitates baby", "baby-like suckling",
                    "模仿婴儿", "模拟婴儿吸吮", "还原婴儿吮吸"],
        "regex": [r"\bmimic(s|king)?\b[^.]{0,30}\bbaby\b",
                  r"模仿\s*婴儿|模拟\s*婴儿|还原\s*婴儿",
                  # ★★ 2026-10-12 补：英文变形 `baby-like … suck(ing|ling)`。
                  #   为什么走 regex 而**不进 synonym**：`sucking` 这个写法**源里没有逐字**
                  #   （已逐表 grep：`风险文案改写建议库` / `W1卖点表达边界` / `品线内容边界规则库`
                  #   三张规则源表 `suck` 命中 **0**）；而 `synonym` 会被当「关键词命中片段」，
                  #   引用契约要求摘录逐字出现在证据单元里 ⇒ 塞进 synonym 的结局是
                  #   **命中后拿不出逐字原文 ⇒ 结论被契约丢弃 ⇒ 「P0 命中却 PASS」**
                  #   （与 H06 `FDA-approved` 同一个教训，见它上面那段注释）。
                  #   ⇒ 变体一律由 regex 承担；regex 的摘录取自**素材本身**，天然可引用。
                  #   范围**收得很紧**：必须 `baby-like` 与 `suck(ing|ling)` **同句**、相隔 ≤24 字
                  #   （不写裸 `suction`，也不写裸 `sucking` —— 那会把泵体结构的正常描述也拦下）。
                  #
                  #   触发它的实证（2026-10-12，回归集 solid 层）：
                  #     素材 RC-11b8f1e6a2c7 逐字含
                  #     `designed to follow a baby-like natural sucking rhythm`
                  #     —— 旧的 literal/synonym/regex 三条路全不中 ⇒ 整段 P0 快路 hit=False
                  #     ⇒ 顶层只出一条 P3 的 U03 ⇒ **PASS**；而历史报告判 BLOCK ⇒ **红线漏放**。
                  #     反向对照：`mimics your baby's natural nursing rhythm` 当时**能**命中
                  #     ⇒ 不是快路失灵，是这一种变形没进表。
                  #   回退：删掉本行，重跑 `kb/.work/l5_export.py --apply`（旧表留档见
                  #   `kb/l5/runs/<RUN>.p0_patterns.superseded.jsonl`）。
                  r"\bbaby[\s-]*like\b[^.]{0,24}\bsuck(?:ing|ling)\b"],
    },
    "U04": {   # 痛点场景 + 消除暗示 → 升级为功效承诺
        "literal": ["painful pumping"],
        "synonym": ["sore nipples", "sore breasts", "clogged ducts"],
        "regex": [r"\b(goodbye|no more|not anymore|relieve[sd]?)\b[^.]{0,40}"
                  r"\b(sore|painful|clogged)\b",
                  r"(告别|不再|摆脱)[^。]{0,20}(疼痛|堵奶|胀痛)"],
    },
    "H06": {   # FDA 表述错误（吸奶器是 cleared/registered，不是 approved/certified）
        # literal 留空是**有意**的：5 条禁用写法已逐字存在于该规则的 forbidden_expression
        # （源：#品线内容边界规则库/recvuJP1LVW6E0/检测关键词，source_sha256 2e8bb36d…），
        # 上面的 src_frags 切分会自动取到；重复列一遍会让溯源混成两处，反而更差。
        "literal": [],
        # 连字符写法**不进 synonym**（2026-09-23 实测更正）：
        # synonym 会被当作「关键词命中片段」，而引用契约要求摘录逐字出现在证据单元里；
        # "FDA-approved" 在源里不存在（源只有空格写法）→ 命中后拿不出逐字原文，
        # 结论会被契约丢弃，表现为「P0 命中却 PASS」。所以改由下面正则承担变体覆盖，
        # 不再用关键词形式宣称一个无法引用的片段。
        "synonym": [],
        "regex": [
            r"\bFDA\s+(approved|certified)\b",       # 源侧「正则表达式」逐字
            r"\bFDA[\s-]*(approved|certified)\b",    # 连字符变体（补源正则的漏洞）
            r"FDA\s*(认证|批准|通过)",                # 中文禁用写法的词形变化
        ],
    },
}

# 白名单：源侧明确允许的表达 / 否定与说明性语境
WHITELIST_COMMON = {
    "negation_patterns": [
        # 2026-10-09：英文侧补**定向**否定比较（实测起因：H08 进 P0 后「not better than medela」被误判 BLOCK）。
        #   有意**不加裸 not** —— 那会把 "Why not choose the safest pump" 里的 safest 一并豁免（漏放）；
        #   只压 not/never/no + 比较级/最高级 这一类固定搭配。
        r"\b(not|never|no)\s+(better|best|safer|safest|superior|more\s+effective)\b[^.]{0,30}",
        # ★★ 2026-10-12 补：**时态/情态否定的缺口**（原交替列只有 `do/does`，没有 `did/will/can/…`）。
        #   实证（`kb/l5/matcher.py --text … --json`，改前）：
        #     `It does not increase milk supply.`      → MISS（被豁免 ✅）
        #     `It doesn't boost your milk supply.`     → MISS（被豁免 ✅）
        #     `It **did not** increase her milk supply.` → **HIT H02** ❌
        #     `Our pump **won't** increase milk supply.` → **HIT H02** ❌
        #   ⇒ 同一件事，**换了时态/情态就不豁免**。与 H02 物主代词缺口同族：**交替列写不全**。
        #
        #   ★ 窗口**故意收紧到 20**（上面那条老的是 40，第一条老的是 30），因为祈使/劝诱句里
        #     也含这些词形 —— 那是**真声明**，吞掉它就是漏放。实测字符距离（逐字数的，不是估的）：
        #       `Don't miss out - it increases your milk supply.`   `Don't`→`milk` = **30**
        #       `Don't wait - it increases your milk supply.`       `Don't`→`milk` = **26**
        #       `Do not wait - it boosts your milk supply!`         `not`  →`milk` = **22**  ← 真声明
        #       `It doesn't appear to boost your milk supply.`      `n't`  →`milk` = **22**  ← 真否定
        #       `It has not been shown to increase milk supply.`    `not`  →`milk` = **24**  ← 真否定（免责声明）
        #     ⇒ **第 4、5 行只差 2 个字**：没有哪个窗口能把「真否定」和「真声明」分开。
        #       取哪一边？取**不豁免**那一边（即 20）—— 本文件上面那条 2026-10-09 的教训逐字写着
        #       「**一个过宽的豁免比不豁免更坏（漏放是真红线）**」。代价照实说：
        #       `It has not been shown to increase milk supply.`（免责声明）**仍会被判 HIT**
        #       —— 这是**已知残留、取舍的结果，不是没修到**，单独记在交付件里。
        #     ⇒ 20 字窗口下：7 条真声明（含上面前三条）**全部仍 HIT**；5 条真否定**全部豁免**。
        #   ★ 三条 pattern 分别管：缩写（`didn't` / `won't` —— `won't` 的词干是 `wo`，
        #     单写 `will` 匹配不上，故列 `wo`/`ca`/`sha`）、分开写（`did not` / `will not`）、
        #     单词形（`cannot` 没有空格，`\s+not` 管不着）。
        #   ★ 与老那条同一条纪律：**只补否定词形，命中词一个不放宽**。
        r"\b(did|do|does|will|would|can|could|shall|should|is|are|was|were|has|have|had|"
        r"wo|ca|sha)\s*n['’]?t\b[^.]{0,20}\b(treat|cure|heal|pain|milk)\b",
        r"\b(did|do|does|will|would|can|could|shall|should|is|are|was|were|has|have|had)"
        r"\s+not\b[^.]{0,20}\b(treat|cure|heal|pain|milk)\b",
        r"\bcannot\b[^.]{0,20}\b(treat|cure|heal|pain|milk)\b",
        r"\b(does\s*n[o']?t|do\s+not|does\s+not|not\s+intended\s+to|never|no\s+claim)\b"
        r"[^.]{0,40}\b(treat|cure|heal|pain|milk)\b",
        # 2026-10-09：中文否定侧补「不会/不具/无」—— 与源侧英文豁免（doesn't treat / does not treat / not to treat）对齐。
        # 起因：H01（医疗功效）按 PRD 进 P0 后实测「不会治疗乳腺炎」被误判 BLOCK；该写法在源侧属豁免语义。
        # 只补否定词形，**不放宽任何命中词**。
        # 2026-10-09 二次补：H03 进 P0 后「未经临床证明」「不是临床证明的」「尚缺乏临床证明」被误判 BLOCK。
        #   只补否定词形与尾组，**命中词一个不放宽**。
        # ★★ 2026-10-09 三次修（**我自己引入的漏放，被 matcher.py --selftest 抓到**）：
        #   本条原先写作 `…|严禁|禁止|无)[^。]{0,20}(治疗|…|催奶|…)` —— 那个**裸 `无`** 就是
        #   英文侧我刻意避开的「裸 not」陷阱的中文翻版：**`无` 是命中词「无痛」的第一个字**，
        #   于是「无痛设计，缓解疼痛，帮助催奶增产」整段被当成「否定语境」豁免 ⇒ **H07/H02 双双漏放**。
        #   实证：`python3 kb/l5/matcher.py --selftest` 两条 positives 由 ✅ 变 ❌ MISS，
        #   诊断脚本打出的豁免片段逐字为 `无痛设计，缓解疼痛，帮助催奶增产`。
        #   ⇒ 只保留**成词的 `无` 短语**（无需/无须/无证据/无依据/无临床/无科学/…），裸 `无` 删除。
        #   纪律：**白名单只加不减**在这一条上不成立 —— 一个过宽的豁免比不豁免更坏（漏放是真红线）。
        r"(不能|不可以|无法|并非|不是|不做|不会|不具|未经|尚缺乏|缺乏|没有|严禁|禁止|"
        r"无需|无须|无证据|无依据|无临床|无科学|无任何|没有任何)[^。]{0,20}"
        r"(治疗|治愈|预防|无痛|增产|催奶|催乳|堵奶|乳腺炎|临床|证明|科学)",
        # 元语境豁免：整行以「禁用表达：/DO NOT SAY:」这类「列禁用词」标记开头时，
        # 该标记到句末之间是在陈述规则（引用被禁词），不是在承诺功效 → 不判 BLOCK。
        # 只豁免到该句结束符，句号之后的内容照常参与匹配。
        r"^\s*(DO\s+NOT\s+SAY|Do\s+not\s+say|禁用表达|禁用词|禁止表达|禁止使用|禁用|禁止|"
        r"不允许|不得使用|违规表述|违规词|高危词)\s*[:：][^。！？!?]{0,200}",
    ],
    "quotation_patterns": [
        r"[「『\"“][^」』\"”]{0,80}[」』\"”]",       # 引用他方 / 规则自身表述
        r"\b(per|according\s+to|as\s+stated\s+in|cited\s+from)\b[^.]{0,30}",
        r"^(依据|来源|原文|条款)[:：]",
    ],
    # 2026-10-09 新增：H05 补「绝对化用语」后必须同时防住的**良性英文最高级**用法。
    # 实测起因：`best regards` 被 `\bbest\b` 判 BLOCK —— 那不是产品宣称。只压这一类固定搭配，
    # 不放宽任何判定：命中若落在这些片段内则不计（与 negation/quotation 同一机制）。
    "benign_superlative_patterns": [
        r"\bbest\s+(regards|wishes|practice|practices|effort|efforts|of\s+luck|"
        r"before|time|interest|known|case|cases)\b",
        r"\b(at|the)\s+very\s+best\b",
        # 中文「最X」的良性用法（实测起因：「我们尽力做到最好」被判 BLOCK）
        r"(尽力|努力|尽量|争取|力求)[^。]{0,6}最好",
        r"最好\s*(在|先|还是|不要|别|能|可以)",
        # ★ 2026-10-10：「最高 + 数值 + 技术单位」是**客观参数**，不是绝对化用语。
        #   实测起因（用户给的第 5 道验证题）：`M5 吸奶器 15 档吸力，最高 -300 mmHg，BPA-free。`
        #   被判 BLOCK，命中词就是本文件给 H05 补的 `最\s*(…|高|…)`。
        #   而**源侧自己的建议写法**就是「吸力表述改客观参数（up to -300 mmHg、15 adjustable levels）」，
        #   中文写「最高 -300 mmHg」正是它的中文表述 ⇒ 拦它等于拦源侧推荐的写法。
        #   只豁免「最高 + 可选(可达/达/到/至) + 含小数点的数值 + 技术单位」这一种形态；
        #   「最高品质」「销量最高」「最高可省 300 元」**照旧命中**（单位表里没有 元/%/倍，
        #   且「可省」不在可选连接词里）。收紧的是**一种良性形态**，没有放宽任何命中词。
        r"最高\s*(?:可达|可到|可至|达|到|至)?\s*[-−]?\s*\d+(?:\.\d+)?\s*"
        r"(?:mmHg|kPa|dB|分贝|档|档位|ml|毫升|oz|盎司|L|升|小时|分钟|秒)",
    ],
    "explanation_patterns": [
        r"\b(example|for\s+instance|e\.g\.|such\s+as|note\s+that)\b[^.]{0,30}",
        r"(例如|示例|举例|说明|注)[:：]",
    ],
}
# 源侧规则自带的允许表达（来自「豁免词」「安全词」字段，仅当该 P0 规则有对应来源时并入）
RULE_WHITELIST = {
    # H05：★ 2026-10-09 按 PRD §7.3 第 3 条**作废**原先的「排名最高级放开」。
    #   原值 ["best","#1","no.1","no. 1","排名第一","第一"] 的出处是源记录 recvuJYdOb1B8v 的
    #   「命中原因」「修改建议」两字段里那句「best/#1/No.1/最佳/最好等排名最高级按 2026-09-09
    #   口径放开，海外广告允许，不再判险」；而 PRD §7.3 把「绝对化用语（最、第一、最佳、100%、
    #   纯天然等）」定为 P0 一票否决 ⇒ 该放开作废，按 PRD 走。
    #   （本字段是说明性的，matcher 不读它；真正生效的是上面 H05 的 regex。）
    "H05": [],
    "H07": ["comfort", "gentle", "discomfort", "缓解胀满不适", "舒适", "温和"],
    "H02": ["relaxation", "relax", "natural let-down", "放松", "自然奶阵"],
    "H04": ["free ibclc service", "免费 ibclc 服务"],
    # H06 的豁免词逐字来自源侧「豁免词」字段（同 anchor、同 source_sha256 2e8bb36d…）。
    # 没有这张白名单，FDA cleared / FDA registered 会被判 BLOCK —— 而它们恰恰是正确写法。
    "H06": ["FDA cleared", "FDA-cleared", "FDA registered", "FDA 注册"],
}

# 词级溯源表：synonym 里凡不是逐字出现在该规则文本里的词，必须在这里声明它等价于规则的哪个词。
# 锚点词必须真的是该规则自己写过的词（命中片段 或 rule_text/建议替换），否则该词判为「凭空」，
# 直接从匹配表里剔除并记进 variant_sources.dropped_ungrounded（见下面 grounding()）。
# 等价关系的实际内容只有两类：同一词的另一语言写法、同一词的连字符/空格写法。
DERIVATION = {
    ('V01', '没坐安全座椅'): '未使用安全座椅',
    ('V01', '未坐安全座椅'): '未使用安全座椅',
    ('V01', '没有安全座椅'): '未使用安全座椅',
    ('V01', '坐在成人腿上'): '安全座椅装副驾',
    ('V01', '坐在大人腿上'): '安全座椅装副驾',
    ('V01', '独自留在车内'): '儿童独留车内',
    ('V01', '单独留在车内'): '儿童独留车内',
    ('V01', '未系安全带'): '成人未系安全带',
    ('V01', '没系安全带'): '成人未系安全带',
    ('V02', '100%'): '最佳',
    ('V02', '第一'): '最佳',
    ('V02', '最好'): '最佳',
    ('V02', '最安全'): '最佳',
    ('V03', '销量第一'): '排名宣称',
    ('V03', '销量领先'): '排名宣称',
    ('V03', '排名第一'): '排名宣称',
    ('V04', '驾驶时怀抱'): '怀抱乘车',
    ('V04', '无人看护'): '无人看护下水',
    ('V05', '儿童出镜'): '未成年人未经授权出镜',
    ('V05', '孩子出镜'): '未成年人未经授权出镜',
    ('V06', '未标注AI'): 'AI 深度合成内容未标识',
    ('V06', 'AI生成未标注'): 'AI 深度合成内容未标识',
    ("H02", "boost milk"): "boost supply",
    ("H02", "maximize milk"): "more milk",
    ("H02", "milk supply boost"): "boost supply",
    ("H02", "下奶"): "增产催奶",
    ("H02", "增加奶量"): "increase milk supply",
    ("H02", "奶量提升"): "increase milk supply",
    ("H04", "doctor recommended"): "ob-gyn recommended",
    ("H04", "doctor-recommended"): "ob-gyn recommended",
    ("H04", "expert recommended"): "recommended by 100+ experts",
    ("H04", "expert-recommended"): "recommended by 100+ experts",
    ("H04", "pediatrician recommended"): "ob-gyn recommended",
    ("H04", "专家认证推荐"): "recommended by 100+ experts",
    ("H04", "医生推荐"): "ob-gyn recommended",
    ("H05", "100%safe"): "100% safe",
    ("H05", "risk-free"): "zero risk",
    ("H05", "完全安全"): "100% safe",
    ("H05", "绝对安全"): "safest",
    ("H05", "零风险"): "zero risk",
    ("H07", "free of pain"): "pain-free",
    ("H07", "relieve pain"): "pain relief",
    ("H07", "不痛"): "无痛",
    ("H07", "告别疼痛"): "缓解疼痛",
    ("H09", "baby-like suckling"): "mimics baby",
    ("H09", "imitates baby"): "mimics baby",
    ("H09", "mimic baby"): "mimics baby",
    ("H09", "mimics a baby"): "mimics baby",
    ("H09", "模仿婴儿"): "模拟复制宝宝",
    ("H09", "模拟婴儿吸吮"): "模拟复制宝宝",
    ("H09", "还原婴儿吮吸"): "模拟复制宝宝",
    ("U04", "sore breasts"): "sore",
    ("U04", "sore nipples"): "sore",
    # ⚠ H06 的连字符写法（FDA-approved / FDA-certified）**故意不在这里登记**。
    # 原因：synonym 会被当作「关键词命中片段」，而引用契约要求摘录逐字出现在证据单元里；
    # 源里只有空格写法，"FDA-approved" 逐字不存在 → 即使登记了，命中后也会被契约丢弃，
    # 表现为「P0 命中却 PASS」（实测：state=PASS + unmet_citation 1 条）。
    # 要让连字符写法也能 BLOCK，得先修引用契约（允许 equivalent_of 用锚点词作摘录），
    # 那是 contract 层改动，不在本次范围。当前连字符覆盖只由 VARIANTS["H06"]["regex"] 承担：
    # 能命中、会记进 unmet_citation，但状态仍是 PASS —— 这是已知开口，见本次修复报告。
}

# ---------- 选取
# 显式准入（2026-09-23 修 P0-2）：H06 是 P0 红线，但上游 l3 给它的 authority 是 inferred，
# 于是被下面的门槛整条排除 —— P0 匹配器里根本没有它，"命中即 BLOCK" 这条路永远抓不到
# 「FDA approved」，只能靠慢一档的规则层兜（实测 trace：P0 0 命中｜规则层 1 命中）。
#
# 为什么是按码准入、而不是放宽 authority 门槛：
#   authority 是上游赋的值，inferred 表示「没标定」，不等于「权威不足」的判定；
#   而这些码的 forbidden_expression / 正则 / 豁免词都逐字来自源侧同一张表的同一条记录
#   （anchor 一致、source_sha256 一致，见 VARIANTS["H06"] 与 RULE_WHITELIST["H06"]）。
#   若放宽门槛，同码的 inferred 重复行（H02/H04/H05/H07/H09 各多一条）会一起进来，
#   直接触发下面的 rule_code 唯一性断言 —— 那是把变体表套错规则的隐患。
# ★ 2026-10-13 加 V01–V06（PRD §7.3 一票否决项第 1/3/4/5/6/7 条；第 2 条「医疗功效宣称」
#   已于 2026-10-09 以 H01 入选）。**照 H01 同一套「按码准入」，不是放宽 authority 门槛。**
#   规则住 `candidates/external_standard.jsonl`（不是 `rules.jsonl` —— 那是措辞库的件，
#   塞进去会让 l7 C2「现行规则库名（1）」判不出唯一库名）。
#   authority=**inferred**（法务未逐条签字 ⇒ **不写 legal**，写了就是过度声明）。
#   回退：删掉 "V01"–"V06" 并重跑 l5_export.py --apply。
# ══ ★★ 2026-10-15 Owner 两条口径（只作用于**本表导出的 P0 模式**）══════════════
#
# 1) **适用内容类型 = 「全部」**。Owner 原话（逐字）：「内容类型写全部」。
#    为什么不是「编一个值」：五张锚点表**结构上都没有内容类型/媒体列**（穷尽取证见
#    `kb/l3/kb_rule_dimensions.py::NOT_DERIVABLE["modality"]`），而 PRD §6.5 要求每条规则
#    都带这一项 ⇒ 留空会被读成「漏填」。「全部」是可读、可核、可替换的取值，且**与现网行为一致**：
#    P0 快路只看文本（文字原件 / 图片 OCR / 视频字幕旁白转成的文本），**不按内容类型过滤**。
#    ⚠️ 边界：**只标本表的 P0 模式**（本文件导出的每一条都是 P0）—— L3 候选行**不动**
#    （L3 的 `applicable_scope` 由 `kb_rule_dimensions.py` 单一派生，不许在这里改第二份）。
#
# 2) **生效版本从 `1.0` 起，改了就递增**。Owner 原话（逐字）：
#    「生效版本就是从1.0开始，修改之后再更新迭代版本就好」。
#    字段名与 PRD §6.5「生效版本」同名。升版时改下面这个常量**不够** ——
#    要按 rule_code 点名（`RULE_VERSION_BY_CODE`）并留痕（谁 / 何时 / 为什么 / 从什么到什么）：
#    `rule_version` 是**逐条**的，不是全局一个数。
#
# ★ 放回退：删掉下面两行常量与 `patterns.append(...)` 里的两个字段，重跑 `--apply`。
P0_CONTENT_TYPE = "全部"
RULE_VERSION_START = "1.0"
#: `rule_code` → 版本。**没点名的取 RULE_VERSION_START**；改了规则才在这里点名升版。
RULE_VERSION_BY_CODE: dict = {}

P0_CODE_ALLOWLIST = {"H06", "H01", "H03", "H08", "V01", "V02", "V03", "V04", "V05", "V06"}
# ★ 2026-10-09 加 H03（未经备案的临床/科学背书）与 H08（无数据支撑的违法对比/贬低竞品）：
#   PRD 依据 = **§7.2 场景域矩阵 #L478「功效宣称与广告用语 | 极高（一票否决域）| P0 | 法务合规红线」**
#   ＋ #L354「P0 = 法律法规、平台政策、一票否决项 … 正则/关键词命中即输出 BLOCK」。
#   Owner 当日裁定「不等法务逐条确认，按 PRD 判规则」。
#   事实链同 H01：两者均来自 L0 飞书源「品线内容边界规则库」（recvuJP1dD4jGX / recvuJP1LVUEBx），
#   源侧「边界类型=严格限制红线、风险等级=高危」；manifest_l3 里本就是 p_level=P0、rule_kind=atomic，
#   唯一不达标是 authority=inferred ⇒ 走 H06 同一套「按码准入」，**不是放宽 authority 门槛**。
#   注：H03 落在「功效宣称」，H08 落在「广告用语」——后者稍宽但同属 P0 域（PRD 未单列"比较广告"）。
#   回退：删掉本集合里的 "H03"/"H08" 重跑 l5_export.py --apply。
# ★ 2026-10-09 加 H01（医疗功效声明）：按 **PRD §7.3「一票否决项（P0 级，命中即 BLOCK）」第 2 条
#   「医疗功效宣称（治疗、预防疾病等）」**判，Owner 当日裁定「按 PRD 判规则，不等法务逐条确认」。
#   事实链（可复核）：① 该规则来自 L0 飞书源「广告文案风控库/品线内容边界规则库」记录 recvuJP1dDHb7E，
#   源侧字段「边界类型=严格限制红线」「风险等级=高危」；② manifest_l3 里它本来就是 p_level=P0、
#   rule_kind=atomic，唯一不达标的是 authority=inferred（不是 expert/legal）；
#   ③ 所以这里走的是与 H06 同一套「按码准入」机制 —— **不是放宽 authority 门槛**，
#   而是 Owner 以 PRD 为依据显式准入（依据与日期都写在本注释里，便于审计）。
#   效力范围：H01 的 72 个触发词（中文 33）从「P1→转人工」变为「命中即 BLOCK、零延迟直返」。
#   回退：删掉本集合里的 "H01" 并重跑 l5_export.py --apply。
P0 = [r for r in latest.values() if r["p_level"] == "P0"]
# ★ 2026-10-17：**缺富化字段不许再 KeyError**（实测缺陷，不是预防性改动）。
#   病灶：外部标准候选件里有 123 条**没有** manifest 富化行（无 `rule_kind` / `authority`）；
#   一旦有哪条被标成 `p_level=P0`（本次人工重标即产生 17 条），下面这行 `r["rule_kind"]`
#   直接 **KeyError 崩掉整个导出** —— 而崩溃路径**在守卫之前**，看起来就像「守卫生效了」。
#   实测：`python3 kb/.work/l5_export.py --apply <RUN>` 当日确实是这条 traceback。
#   口径（**不放松任何门槛**）：没有富化的行**进不了 P0 快路**（它连 atomic/authority 都判不了），
#   但必须**被计数、被列出来**（`exc["P0_but_no_enrich"]`），不许静默消失。
_P0_ENRICHED = [r for r in P0 if "rule_kind" in r and "authority" in r]
_P0_NO_ENRICH = [r for r in P0 if r not in _P0_ENRICHED]
_sel_base = [r for r in _P0_ENRICHED if r["rule_kind"] == "atomic" and r["authority"] in ("expert", "legal")]
_sel_codes = {r.get("rule_code") for r in _sel_base if r.get("rule_code")}
_sel_extra = [r for r in _P0_ENRICHED
              if r["rule_kind"] == "atomic"
              and (r.get("rule_code") or "") in P0_CODE_ALLOWLIST
              and (r.get("rule_code") or "") not in _sel_codes]
sel = _sel_base + _sel_extra
exc = collections.Counter()
# ── 批次16 · 0-4：**每条 P0 的处置都要落到可查产物**（不只是 print 一行计数器）──────
# 要求（用户批16 0-4）：15 条无码 P0 现在靠 `exc` 计数兜着 —— 但「计数」不等于「可查」：
#   计数只说明「有几条」，不说明「**哪一条**、因为什么」。**不许出现无原因地被丢掉。**
# ⇒ 这里把每条 P0 的 (rule_id, rule_code, 处置, 原因) 逐条记下来，随后写进 runs 产物。
p0_disposition = []
for r in latest.values():
    rid = r.get("rule_id")
    code = (r.get("rule_code") or "").strip()
    if r["p_level"] != "P0":
        exc["non_P0"] += 1
    elif "rule_kind" not in r or "authority" not in r:
        exc["P0_but_no_enrich"] += 1
        p0_disposition.append({"rule_id": rid, "rule_code": code, "disposition": "excluded",
                               "reason": "P0_but_no_enrich",
                               "why": "manifest_l3 里没有该 rule_id 的富化行（rule_kind/authority 缺失）"
                                      " ⇒ 判不了 atomic/authority，故不进快路（**不是**门槛放宽的结果）"})
    elif r["rule_kind"] != "atomic":
        exc["P0_but_inductive"] += 1
        p0_disposition.append({"rule_id": rid, "rule_code": code, "disposition": "excluded",
                               "reason": "P0_but_inductive",
                               "why": "rule_kind=%s（非 atomic）—— 由多条证据归纳出的模式，"
                                      "不进「命中即 BLOCK」的确定性匹配器" % r.get("rule_kind")})
    elif r["authority"] not in ("expert", "legal"):
        if code in P0_CODE_ALLOWLIST:
            exc["P0_admitted_by_allowlist"] += 1
            p0_disposition.append({"rule_id": rid, "rule_code": code, "disposition": "included",
                                   "reason": "P0_admitted_by_allowlist",
                                   "why": "authority=%s 低于门槛，但码在 P0_CODE_ALLOWLIST=%s 里，"
                                          "按显式准入放进（H06 的注释说明了为什么）"
                                          % (r.get("authority"), sorted(P0_CODE_ALLOWLIST))})
        else:
            exc["P0_but_authority_insufficient"] += 1
            p0_disposition.append({"rule_id": rid, "rule_code": code, "disposition": "excluded",
                                   "reason": "P0_but_authority_insufficient",
                                   "why": "authority=%s 不在 (expert,legal)，且码 %r 不在 "
                                          "P0_CODE_ALLOWLIST=%s 里 ⇒ 按门槛排除"
                                          % (r.get("authority"), code, sorted(P0_CODE_ALLOWLIST))})
for r in sel:
    _rid = r.get("rule_id")
    if not any(d["rule_id"] == _rid for d in p0_disposition):
        p0_disposition.append({"rule_id": _rid, "rule_code": (r.get("rule_code") or "").strip(),
                               "disposition": "included", "reason": "passed_threshold",
                               "why": "P0 且 atomic 且 authority 达门槛（或经白名单）"})
print(f"P0 {len(P0)} 条 → 入选 {len(sel)}（其中准入白名单 {len(_sel_extra)}） | 排除 {dict(exc)}")
_p0_exc = [d for d in p0_disposition if d["disposition"] == "excluded"]
_p0_inc = [d for d in p0_disposition if d["disposition"] == "included"]
print(f"  [处置留痕] P0 共 {len(p0_disposition)} 条 = 入选 {len(_p0_inc)} + 排除 {len(_p0_exc)}"
      f"（**每条都有 reason/why，无原因丢弃 = 0**）")
assert len(_p0_inc) == len(sel), (len(_p0_inc), len(sel))

# ══════════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-17：**P0 快路不许被静默扩容**（fail-closed 守卫）
# ══════════════════════════════════════════════════════════════════════════════
# 为什么加（不是预防性设计 —— 它是本次数据落库**测出来的**直接后果）：
#   本文件的 P0 选取口径是 `p_level == "P0"`，而 `p_level` 的**人工重标**
#   （`kb/l3/registry/rule-taxonomy.json`，2026-10-17 落库）把 P0 从 28 条改到 63 条
#   ⇒ 同一份 `_sel_base` 门槛下，可导出条数从 **17 变 19**（多出 W-1.49 / W-1.5）。
#   而 `p0_patterns.jsonl` 是 **≤1s 命中即 BLOCK、置信度 1.0** 的那张表，
#   它另有一份法务逐条签字台账（`kb/l5/registry/p0-legal-signoff-ledger.json`）。
#   ⇒ 让它跟着 `p_level` 自动长，等于「改一次分类顺手把红线扩了」，且没有人会被问到。
# 口径（两句话）：
#   · 导出集合与**现表**（`kb/l5/p0_patterns.jsonl`）不一致 ⇒ **拒写**，除非显式
#     `--accept-p0-expansion`（人点头）或环境变量 `KB_P0_ACCEPT_EXPANSION=1`；
#   · 拒写时把**多了哪几条 / 少了哪几条**逐条打出来（article_no + rule_id），
#     并把它们写进 runs 产物 ⇒ 不是一句「不一致」，是可直接拿去签字的清单。
def _current_pattern_ids():
    p = f"{L5}/p0_patterns.jsonl"
    out = set()
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.strip():
                try:
                    out.add(json.loads(line).get("rule_id"))
                except ValueError:
                    pass
    return out


_cur_ids = _current_pattern_ids()
_new_ids = {r.get("rule_id") for r in sel}
_added, _removed = sorted(_new_ids - _cur_ids), sorted(_cur_ids - _new_ids)
_accept = ("--accept-p0-expansion" in sys.argv) or os.environ.get("KB_P0_ACCEPT_EXPANSION") == "1"
p0_expansion_guard = {"current": len(_cur_ids), "computed": len(_new_ids),
                      "added": _added, "removed": _removed, "accepted": bool(_accept)}
if (_added or _removed) and not _accept:
    print("⛔ 拒写（P0 快路扩容守卫）：本次可导出 %d 条 ≠ 现表 %d 条"
          % (len(_new_ids), len(_cur_ids)))
    for _rid in _added:
        _r = latest.get(_rid) or {}
        print("   ＋ 新增 %s ｜ %s ｜ p_level=%s"
              % (_r.get("article_no"), _rid, _r.get("p_level")))
    for _rid in _removed:
        _r = latest.get(_rid) or {}
        print("   － 移除 %s ｜ %s ｜ p_level=%s"
              % (_r.get("article_no"), _rid, _r.get("p_level")))
    print("   → 快路是「命中即 BLOCK + 置信度 1.0」，另有法务签字台账；扩容必须人点头。")
    print("   → 确认要扩：`python3 kb/.work/l5_export.py --apply --accept-p0-expansion`"
          "（并同步补 `p0-legal-signoff-ledger.json`）")
    print("   → 不扩：本次**不写任何产物**；p_level 的人工重标仍在 L3 生效（规则层判 BLOCK），"
          "两条轴互不牵连。")
    raise SystemExit(4)

# 变体表按 rule_code 查表，因此入选规则的 rule_code 必须唯一，否则会把 A 规则的变体套到 B 规则上。
# （全套 1018 条里 rule_code 并不唯一：品线内容边界规则库复用同一套码 H01-H09/M01-M07/U01-U04，但那些是
#  authority=inferred，已被门槛排除；这里只校验入选集合内部不重码。）
_dup = collections.Counter(r.get("rule_code") for r in sel)
dups = {k: v for k, v in _dup.items() if v > 1}
print(f"入选集合 rule_code 唯一性检查：{'PASS' if not dups else 'FAIL ' + str(dups)}")
assert not dups, dups
code_collision_note = ("rule_code 在全套规则里不唯一（品线内容边界规则库复用 H01-H09/M01-M07/U01-U04 码，"
                       "authority=inferred 已按门槛排除）；入选集合内部已校验无重码，变体表按 rule_code 查表安全")

#: 规则自己的**边界表述**（源字段「触发原因」/「边界内容」，逐字，一字未改）。
#   为什么要有这一格（2026-10-21，Owner 验收）：Owner 是**按规则库的「触发原因」列逐条送审**的，
#   于是「这句话命不命中自己那条规则」本身就成了验收口径。而 P0 词表原先只收「检测关键词」，
#   边界表述从来没进过 ⇒ H03 `未经备案的临床/科学背书`、H06 `FDA 表述错误（…）`、
#   H08 `无数据支撑的违法对比 / 贬低竞品`、H09 `智能闭环/仿生虚假宣称（…）` 四条送审回来是 PASS。
#   溯源：四句逐字来自 L0「品线内容边界规则库」（recvuJP1dD4jGX / recvuJP1LVW6E0 / recvuJP1LVUEBx /
#   recvuJYdOb61lT）的触发原因字段；H03/H06/H08 也落在各自 `rule_text` 的「边界：…」段里，
#   H09 落在 `reason` 里 —— 故 `grounding()` 的 rule 池自本日起含 `reason`。
#   ⚠️ 代价（明写）：`禁用表达：<边界表述>` 这类清单行也会 BLOCK；取不漏一侧。
BOUNDARY_TERMS = {
    "H03": ["未经备案的临床/科学背书"],
    "H06": ["FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）"],
    "H08": ["无数据支撑的违法对比 / 贬低竞品"],
    "H09": ["智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；"
            "W1当前为用户主动调节+保存程序，非闭环生理识别"],
}

#: 规则名 / 边界表述：逐字出现即命中，**否定白名单一律不豁免**（它是规则名，不是被否定的宣称）。
#   病灶（2026-10-21 实测）：H03 的边界表述「未经备案的临床/科学背书」整句落在否定白名单
#   `(…|未经|…)[^。]{0,20}(…|临床|…)` 的跨度里（「未经」+「备案的」+「临床」）⇒ 只加词仍 0 命中。
#   消费方：`kb/l5/matcher.py` 的 `compile_patterns()` / `_line_hits()`（不是注释，是判据）。
WHITELIST_EXEMPT = {"H03": ["未经备案的临床/科学背书"]}


# ---------- 生成模式
def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r'\s+', ' ', s).strip()

patterns, no_pattern = [], []


def grounding(term, code, pool_source, pool_rule):
    """给每个词一个可机验的来源标记；返回 (basis, anchor)。basis=ungrounded 表示凭空，必须剔除。"""
    t = norm(term).casefold()
    if t in pool_source:
        return "verbatim_source", term
    if t in pool_rule:
        return "verbatim_rule_text", term
    anc = DERIVATION.get((code, norm(term)))
    if anc and norm(anc).casefold() in (pool_source + " " + pool_rule):
        return f"equivalent_of:{anc}", anc
    return "ungrounded", None


for r in sorted(sel, key=lambda x: str(x.get("rule_code"))):
    code = r.get("rule_code") or ""
    v = VARIANTS.get(code)
    if not v:
        no_pattern.append({"rule_id": r["rule_id"], "rule_code": code,
                           "reason": "该规则的可匹配片段无法从源侧「命中片段/检测关键词」直接得到，"
                                     "且不属于已定义的语义族，故不生成 pattern"})
        continue
    # 字面片段：全部来自源侧命中片段。分隔符两类都要切：
    #   「；」= L3 汇总多个来源记录时的连接符；「,，」= 源侧单元格内部的并列写法。
    # 不切开就会拼出一个源里不存在的长串（如 "recommended by 100+ experts;ob-gyn recommended"），
    # 导致该片段永远匹配不上。切分只是拆回源侧本来就并列的片段，不新增词。
    src_frags = [norm(x) for x in re.split(r'[,，;；]', r["forbidden_expression"]) if norm(x)]
    # ★★ 2026-10-19（Owner 裁定）：**显式出列**（VARIANTS 的 `exclude`）。
    #   为什么需要这个机制、而不是直接把词从 literal/synonym 删掉：
    #   `src_frags` 来自**源侧** `forbidden_expression`（飞书源只读，删不掉），
    #   只改 VARIANTS 的词会被 src_frags 在导出时补回来 ⇒ 看着改了、其实没生效。
    #   出列的词**保留痕迹**：写进 `variant_sources.dropped_by_ruling`，报告/核查看得见，不是静默消失。
    _excl = {norm(x) for x in (v.get("exclude") or []) if norm(x)}
    src_frags = [x for x in src_frags if x not in _excl]
    lit = sorted({norm(x) for x in (src_frags + v["literal"]) if norm(x) and norm(x) not in _excl})
    syn = sorted({norm(x) for x in v.get("synonym", []) if norm(x) and norm(x) not in _excl})
    rx = v.get("regex", [])
    pool_source = norm(r["forbidden_expression"]).casefold()
    # ★ 2026-10-21：`reason` 也进 rule 池 —— H09 的边界表述逐字住在 `reason` 里（不在 rule_text）
    pool_rule = norm((r.get("rule_text") or "") + " " + (r.get("suggested_replacement") or "")
                     + " " + (r.get("reason") or "")).casefold()

    # ---- 词级溯源：逐词给 basis，凭空的词不进匹配表
    match_terms, dropped = [], []
    for term in lit + syn:
        basis, anchor = grounding(term, code, pool_source, pool_rule)
        if basis == "ungrounded":
            dropped.append(term)
            continue
        match_terms.append({"term": term, "basis": basis, "anchor": anchor})
    # ★ 2026-10-21：边界表述直接进匹配表（溯源由 BOUNDARY_TERMS 那张表本身承担，见其注释）
    bnd = [norm(x) for x in (BOUNDARY_TERMS.get(code) or []) if norm(x)]
    for _t in bnd:
        match_terms.append({"term": _t, "basis": "verbatim_rule_text", "anchor": _t})
    plist = [m["term"] for m in match_terms]
    # 去重：已被更长的词覆盖的短词不再重复计入 keyword
    plist = [p for p in plist if not any(p != q and p in q for q in plist)]
    match_terms = [m for m in match_terms if m["term"] in plist]
    wl = (list(WHITELIST_COMMON["negation_patterns"])
          + list(WHITELIST_COMMON["quotation_patterns"])
          + list(WHITELIST_COMMON.get("benign_superlative_patterns") or []))
    if code in RULE_WHITELIST:
        wl_note = RULE_WHITELIST[code]
    else:
        wl_note = []
    patterns.append(dict(
        pattern_id="p-" + hashlib.sha1(f"{EXPORTER_VERSION}|{r['rule_id']}".encode()).hexdigest()[:16],
        rule_id=r["rule_id"], rule_code=code,
        # ★ 2026-10-10：条款号落到模式表顶层（工单 10/12 行 · 周一 #2「P0 侧条款号补字段」）。
        #   值**从 L3 候选行透传**，不在这里 join —— 11 条 P0 规则在 L3 里 11/11 自带
        #   `article_no`（2026-10-10 实测），再 join 一次等于给同一件事造第二个真源。
        #   为什么非要有它：目标 18 要求「P0 红线上线前由法务逐条确认（留签署记录）」，
        #   而 `p0_fastpath._l4_clause()` 是**运行时**才去 L4 查号的 ⇒ 法务拿着一张
        #   不含条款号的模式表**没法逐条签**。取不到就写 None（**不编**）。
        article_no=(str(r.get("article_no") or "").strip() or None),
        article_no_source=(("kb/l3/candidates/%s.jsonl#article_no" % _RID_SRC.get(r["rule_id"], "rules"))
                           if str(r.get("article_no") or "").strip() else None),
        anchor=r["anchor"], source_sha256=(r["evidence_units"][0] or {}).get("source_sha256"),
        type="keyword" if plist else "regex",
        patterns=plist,
        match_terms=match_terms,
        regex_patterns=rx,
        whitelist=wl,
        whitelist_allowed_expressions=wl_note,
        # ★ 2026-10-21：规则名/边界表述（逐字出现即命中，白名单不豁免）—— 见上方常量注释
        whitelist_exempt_terms=list(WHITELIST_EXEMPT.get(code) or []),
        suggested_replacement=norm(r["suggested_replacement"]),
        match_note="BLOCK",
        # ★ 2026-10-15：PRD §6.5 的「适用内容类型」与「生效版本」（口径见文件上方两段注释）。
        content_type=[P0_CONTENT_TYPE],
        rule_version=RULE_VERSION_BY_CODE.get(code, RULE_VERSION_START),
        p_level=r["p_level"], authority=r["authority"],
        evidence_units=r["evidence_units"],
        variant_sources={"literal_from_source": lit, "synonym_family": syn, "regex": rx,
                         "dropped_ungrounded": dropped,
                         "boundary_from_source": bnd,
                         # 2026-10-19：按裁定出列的词（源侧仍有，本表不再匹配）—— 可核、不静默
                         "dropped_by_ruling": sorted(_excl)},
    ))
    if dropped:
        print(f"  ! {code} 剔除无溯源的词 {dropped}")

# ---------- 落盘
with open(f"{L5}/p0_patterns.jsonl", "w", encoding="utf-8") as fh:
    for p in patterns:
        fh.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L5}/index/l5.jsonl", "w", encoding="utf-8") as fh:
    for p in patterns:
        fh.write(json.dumps({"pattern_id": p["pattern_id"], "rule_id": p["rule_id"],
                             "type": p["type"], "match_note": p["match_note"]},
                            ensure_ascii=False, sort_keys=True) + "\n")

n_pat = sum(len(p["patterns"]) for p in patterns)
n_rx = sum(len(p["regex_patterns"]) for p in patterns)
n_wl = sum(1 for p in patterns if p["whitelist"])
json.dump({"exporter_version": EXPORTER_VERSION, "kb_version": KB_VERSION,
           "selection": {"p_level": "P0", "rule_kind": "atomic", "authority": ["expert", "legal"],
                         "code_allowlist": sorted(P0_CODE_ALLOWLIST),
                         "code_allowlist_note": "上游 authority=inferred 但证据逐字可溯的 P0 红线，"
                                                "按码准入（2026-09-23 补 H06）；不是放宽 authority 门槛"},
           "rule_code_uniqueness": code_collision_note,
           "excluded": dict(exc),
           "p0_disposition": p0_disposition,
           "p0_disposition_note": "每条 P0 的处置与原因；**无原因丢弃 = 0**（批次16 0-4）",
           "variant_policy": {
               "literal_from_source": "全部取自源侧规则 evidence 的「命中片段/检测关键词」，"
                                      "按「；」(L3 跨记录连接符) 与「,，」(源侧单元格内并列) 切开后逐条成 pattern",
               "synonym_family": "同一语义族的等价说法，且必须出现在该规则的 suggested_replacement / rule_text 的表述范围内",
               "regex": "处理词形变化（复数/时态/连字符/中英变体）与「场景+消除暗示」组合式命中",
               "no_new_knowledge": "每条 pattern 都回指已存在的 rule_id；未引入源里没有的事实",
               "word_level_grounding": "逐词给出 basis：verbatim_source（逐字来自该规则的命中片段）/"
                                       "verbatim_rule_text（逐字来自该规则的 rule_text 或建议替换）/ "
                                       "equivalent_of:<锚点词>（同一词的另一种语言或连字符写法，锚点词必须是该规则自己写过的词）。"
                                       "三种都对不上 → 判为凭空，不进匹配表，记进 variant_sources.dropped_ungrounded",
           },
           "term_grounding": {m["term"]: m["basis"] for p in patterns for m in p["match_terms"]},
           "whitelist_policy": {
               "negation": WHITELIST_COMMON["negation_patterns"],
               "quotation": WHITELIST_COMMON["quotation_patterns"],
               "rule_specific_allowed": RULE_WHITELIST,
               "why": "没有例外清单，误报会把 BLOCK 精确率（PRD 要求 ≥95%）拉下来",
           },
           "normalization": {"unicode": "NFKC", "whitespace": "collapse", "casefold": True,
                             "note": "匹配前统一做 NFKC + 空白折叠 + casefold，抵消全角/大小写/多空格差异"},
           "match_note_enum": ["BLOCK"]},
          open(f"{L5}/registry/l5.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(no_pattern, open(f"{L5}/registry/l5_no_pattern.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
basis_cnt = collections.Counter(m["basis"].split(":")[0] for p in patterns for m in p["match_terms"])
n_drop = sum(len(p["variant_sources"]["dropped_ungrounded"]) for p in patterns)
print(f"模式 {len(patterns)} 条 | keyword 式 {n_pat} | regex 式 {n_rx} | 有白名单 {n_wl} | 无法生成 {len(no_pattern)}")
print(f"词级溯源 {dict(basis_cnt)} | 剔除凭空词 {n_drop}")
json.dump({"patterns": len(patterns), "keyword": n_pat, "regex": n_rx, "whitelist": n_wl,
           "no_pattern": no_pattern, "excluded": dict(exc), "p0_total": len(P0),
           "selected": len(sel), "term_basis": dict(basis_cnt), "dropped_ungrounded": n_drop,
           "match_terms": {p["rule_code"]: p["match_terms"] for p in patterns}},
          open("kb/.work/l5_patterns.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
