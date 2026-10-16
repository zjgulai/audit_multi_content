# L6 层执行留痕 · RUN=RT-20261005-PLAYARD-VIDEO-L6

- 层：L6（召回层）
- RUN：`RT-20261005-PLAYARD-VIDEO-L6`（未改名）
- 档位：**预演档 / 只读**（全程未加 `--apply`、未加 `--write-gate`、未加 `--allow-beyond-policy`；本层本次三条件一条都不满足，只走查询档）
- 执行时间：2026-10-05 10:45:23 → 11:01（本机时区 +0800；闸门实际成功于第 6 次尝试 10:47:35）
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（`kb/` 为其下的权威库）
- **`skill_loaded: kb-recall`** —— 用 **skill 工具真加载**（不是"知道有它"）；`kb-recall` = `kb/l7/registry/layers.yaml` L6 段 `skill:` 字段（第 452 行）的唯一真源值。加载到的正文里 §3「查询档不写」与「不把 Top-N 当命中」两条按本次只读档执行。

## 第 2 步 · 本层 engine 清单（抄自 `kb/l7/registry/layers.yaml` L6 段，第 462-488 行；未从别处手抄）

`skill:` = `[kb-recall]`（第 452 行）。`engine:` 共 **6** 个（含批次 4/5/6/7 补登）：

| # | engine | 补登批次 | 带 ★ |
|---|---|---|---|
| 1 | `kb/.work/l6_scope.py` | 批次6 补登（2026-10-01） | 否 |
| 2 | `kb/.work/l6_build.py` | — | 否 |
| 3 | `kb/.work/l6_bench.py` | — | **★ 驱动循环默认跳过**（无预演档，`:119` 无条件写 `kb/l6/benchmark.json`） |
| 4 | `kb/.work/l6_integrity.py` | 批次7 补登（2026-10-01） | 否 |
| 5 | `kb/.work/l6_selftest.py` | 批次5 补登（2026-10-01） | 否 |
| 6 | `kb/.work/l6_report.py` | 批次4 补登（**L6 落章引擎**） | 否 |

**★ 标记只有 1 个**：`l6_bench.py` ⇒ **本次未跑它**（跑它＝无条件写 `kb/l6/benchmark.json`，与"严格只读"冲突）。其余 5 个引擎全部以预演档跑过。
（清单里**没有**第二个带 ★ 的引擎。）

## exit_code 逐条

| # | 命令 | exit_code | 说明 |
|---|---|---|---|
| 3 | `sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L6 --gate-only --run RT-20261005-PLAYARD-VIDEO-L6` | **0**（第 6 次尝试） | 前 5 次 exit 2 = 锁被别的会话持有 |
| 4-1 | `sh kb/kbpy .work/l6_scope.py --run RT-20261005-PLAYARD-VIDEO-L6` | **1** | 对账 FAIL（基准落伍，见 blockers B2） |
| 4-2 | `sh kb/kbpy .work/l6_build.py RT-20261005-PLAYARD-VIDEO-L6` | **0** | 预演，零写入 |
| 4-3 | `sh kb/kbpy .work/l6_integrity.py RT-20261005-PLAYARD-VIDEO-L6` | **0** | **故意早退**（设计内），零副作用 |
| 4-4 | `sh kb/kbpy .work/l6_selftest.py --run=RT-20261005-PLAYARD-VIDEO-L6` | **0** | 预演；**只判了 5/14 条查询**（见 blockers B4） |
| 4-5 | `sh kb/kbpy .work/l6_report.py RT-20261005-PLAYARD-VIDEO-L6 --skill kb-recall` | **0** | 预演落章；`run verdict = FAIL` |
| — | `kb/.work/l6_bench.py`（★ 标记） | **未跑** | 设计内跳过，不加开关绕过 |
| 附 | `sh kb/kbpy l7/scripts/l6_gate.py`（只读档，为取"没跑的 4 项"原文） | **0** | 只读，未写任何文件 |
| 5 | 三条 `l6/retriever.py --query … --top 5` | **0 / 0 / 1** | 第 3 条的人类可读输出崩了（见 blockers B5）；`--json` 档同查询 exit 0 |

## 第 3 步 · 闸门 stdout 原文（逐字，全量）

```
[层表核对] STAMP_SPEC 7 条全部能在 layers.yaml 本层 engine: 里找到 ✅
====================================================================================
知识库 L0–L7 执行编排器 · --sync ｜ 预演（不带 --apply） ｜ run_id=RT-20261005-PLAYARD-VIDEO-L6
====================================================================================
锁：已持锁 pid=79791 run_id=RT-20261005-PLAYARD-VIDEO-L6
[写档闸门] **未带 --write-gate 凭据** → 本次按「各层只许只读档」对待；层引擎不得带 --apply。凭据表见 kb/l7/registry/write-gate.yaml
[L6] ⚠️ 写档闸门：**未带 --write-gate 凭据** → 本次按「各层只许只读档」对待；层引擎不得带 --apply。凭据表见 kb/l7/registry/write-gate.yaml
[L6] 闸门：过 ｜ exit=0 ｜ 退出码：0
[L6] via-skill：本层该调的 skill ＝ kb-recall
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l6_scope.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l6_build.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l6_bench.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l6_integrity.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l6_selftest.py
        ↳ 该 skill 内部照 layers.yaml 跑：kb/.work/l6_report.py
[L6] via-skill：引擎交给 kb-recall（本编排器不跑；它只跑闸门 + 记账 + **--skill 透传**）
[L6] --skill 透传：l6_report.py RT-20261005-PLAYARD-VIDEO-L6 --skill kb-recall ［预演档：未获本层写档凭据］
[L6] 落章引擎 exit=0 ｜ 产物变化 0 个
        [dry-run] 台账 → kb/l6/runs/RT-20261005-PLAYARD-VIDEO-L6-dryrun.json（顶层 skill=kb-recall）
        run verdict = FAIL
[记账] --gate-only：本次**不写** kb/l7/runs/（只过闸门 + 持锁/释放）—— 最终态由带 --invoked 的那次记账落，一个 RUN 在 index.jsonl 里只留 1 行
[记账] 层侧落章实测：applied 0 ｜ dry 1 ｜ unknown 0 ｜ 读错 0 → human_involved=False ｜ verdict=全走完（预演 · 未落盘 · 非执行证据）
------------------------------------------------------------------------------------
结论：L6 全部走完（预演（不带 --apply））
提示：这是预演。真正落盘要加 --apply，且当前白名单只开 ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']。
```

**要抄的那一行**：`[L6] 闸门：过 ｜ exit=0 ｜ 退出码：0`
**透传那一行**：`[L6] --skill 透传：l6_report.py RT-20261005-PLAYARD-VIDEO-L6 --skill kb-recall ［预演档：未获本层写档凭据］`
**run verdict = `FAIL`**（落章引擎的 verdict，不是闸门的 verdict；机制见 blockers B3）
**退出码 = 0**

### 本层闸门是**只读档** —— 明写没跑的 4 项（照抄 `l6_gate.py` 说明项 N2 原文）

```
说明项 N2：**本闸门没跑的 4 项**（要写索引/要人看，只在完整档跑）：③ 重跑幂等（要 --apply 重跑建索引）；⑥ 分段拼接逐字；⑦ 倒排与词频自洽；⑨ 冻结基线（活库模式下本就该变）
```

⚠️ **不许把「闸门过」说成「索引全对上」**：本次闸门**只**过了只读 4 项（① 计数一致 ② 向量可回指 ④ 编号同源 ⑤ 版本纪律），上面 ③⑥⑦⑨ 这 4 项**没跑**。完整档要人跑 `kb/.work/l6_integrity.py <RUN> --apply`，本次**未跑**（要写索引，属写档）。
闸门自身结论原文：`结论：✅ 过（只读 4 项全过；完整档另行）`；另有两条说明项原文：
```
说明项 N3：注册表计数器与产物不一致（不是红）—— docs.jsonl 4261 行 vs counts.bm25_indexed 4260；注册表计数器与产物不一致；产物侧 docs.jsonl == 可用单元数
说明项 N1：bm25_failed = 1（失败项须在层证据里逐条有原因）
```
（`bm25_failed` 的 1 条原因出自 dryrun 件：unit_id `00fa63e07ffead5207da`，`#广告文案明细/recvuMGgT9Nm8K/广告名称`，`文本切不出任何词元（正文只有 '-'）`。）

## 第 5 步-1 · 落章件字段原值

- 路径：`kb/l6/runs/RT-20261005-PLAYARD-VIDEO-L6-dryrun.json`（mtime 2026-10-05 10:53）
- `run_id` = `"RT-20261005-PLAYARD-VIDEO-L6"`
- `skill` = `"kb-recall"` ✔（与 `layers.yaml` L6 段 `skill:` 一致）
- `dry_run` = `true`
- `applied` = `false`
- `pipeline_run_id` = `"RT-20261005-PLAYARD-VIDEO-L6"`
- `verdict` = `"FAIL"`
- 附带：`skill_source` = `"--skill 参数（调用者读 layers.yaml 本层 skill: 后传入；本脚本不硬编码）"`；`integrity_verdict` = `"PASS"`；`dry_run`/`applied` 为真值 ⇒ 本次是**机制证据**，不是执行证据。
- 另有 `kb/l6/runs/RT-20261005-PLAYARD-VIDEO-L6-selftest-dryrun.json`（`l6_selftest.py` 的预演件，**不带** `skill` 键、不是落章）。其 `query_count=14`、`judged_count=5`、`preview_of="kb/l6/selftest.json"`，自述 `note=预演档：kb/l6/selftest.json 未被写入、未归档；本件不是落章（无 skill 键）`。

## 第 5 步-2 · 三条只读召回实测（**候选**，不是"命中"；Top-5）

说明：L6 **无命中阈值**，检索器一律返回 Top-N ⇒ 下面一律称**候选**。模式默认 `auto`（本次全部解析为 `hybrid`）。

### 查询 1：`baby playard one-click fold safety`（exit 0；`lists_used=[bm25_en, vector]`）

| rank | unit_id | score | sha256(前16) | 锚点 | 片段 |
|---|---|---|---|---|---|
| 1 | `1bc36c3f619d48233899` | 0.02881 | `f9d17d755dad8efd` | `#l.1-171` | (“I like the way BEHAVIOR 215 you played nicely when I was talking to Jessica. Now you and I are going to do something special together!”). A trip to |
| 2 | `75c2dccb9660983fd423` | 0.02789 | `d45e9b4d54898eee` | `#l.1-55` | BABY Aftermarket products (items that are made for car seats but are sold sepa - rately from the car seat) are not regu - lated, do not have to pass a |
| 3 | `f415693702b3c7845873` | 0.02762 | `d45e9b4d54898eee` | `#l.1-300` | . The gagging will ease up as baby learns to cope with the solids and the lumps. Just be sure to keep a careful watch on your little one as he munches |
| 4 | `322d0163d2cdf55ba61f` | 0.02524 | `d45e9b4d54898eee` | `#l.1-59` | amily in case you die. Such insurance provides a benefit upon death without any cash accumu- lation. You should also consider dis - ability insurance |
| 5 | `d611ed3081742b9970ad` | 0.02410 | `d45e9b4d54898eee` | `#l.1-129` | infant seat, use a convertible seat, YOUR NEWBORN 157 which can accommodate larger babies in the rear-facing position. ■ Place the infant safety seat, |

### 查询 2：`playard 婴儿游戏床 折叠 安全`（exit 0；`lists_used=[bm25_en, bm25_zh, vector]`）

| rank | unit_id | score | sha256(前16) | 锚点 | 片段 |
|---|---|---|---|---|---|
| 1 | `c071337965568e207c7a` | 0.03151 | `b3bd94713f7f86a3` | `#l.1-5` | 关，最常见 的是甜品所致的窒息，占所有窒息意外的32%。 其他可能引起窒息的食物包括鱼骨头，饼干，小 块水果。 下面是婴儿或儿童窒息的所有体征。… |
| 2 | `86922699ee3fff7aea10` | 0.02991 | `b3bd94713f7f86a3` | `#l.1-6` | 大， 能装下各种玩具， 同时孩子能随意 看到并拿到里面 的东西。 问与答 给孩子买玩具箱时要注意 什么？ 安全储藏玩具很重要， 玩具箱本身可能有害。… |
| 3 | `343bb6641a2d591f5a2e` | 0.02896 | `0d639bdde9d504b0` | `#l.1-3` | 宝的絡膊能触到摇篮边的话， 在挨着自己大床的摇篮里；当 就表明摇篮开始拘束他了，让 宝宝大一点儿，能够独自睡在 他感觉不舒服。 好的摇篮应当是既结实，… |
| 4 | `8f9f176938ca488c7bb0` | 0.02881 | `b3bd94713f7f86a3` | `#l.1-3` | 放下时，宝宝最容易跌落。确 定小床获得了安全认证。小床 必须依法符合安全标准。如果 您购买这种符合质量标准的小 床，就能保证孩子不会轻易跌 落或在小床中伤及自己。… |
| 5 | `9c41b65784b61714ff78` | 0.02711 | `1d95d1f1236b6f33` | `#负面样本/recvw7XIUgXEvk/具体原因/分析` | 具体原因/分析: 【原则性错误】视频 图 1 主标题醒目柔和，画面是宝宝跟爸爸同床，并且睡在柔软的枕头上（。 【问题要点】 1. 主标题醒目柔和，… |

### 查询 3：`Built to last durable playard`（人类可读档 **exit 1**；`--json` 档 exit 0）

| rank | unit_id | score | sha256(前16) | 锚点 | 片段 |
|---|---|---|---|---|---|
| 1 | `2815cff1afe57b86cd22` | 0.02513 | `f9d17d755dad8efd` | `#l.1-332` | eds, and hobby areas) are chock-full of toxic products, sharp objects, and other potential hazards, so: « If your garage is attached to your house, ke |
| 2 | `c14a40999cbc0a977c1e` | 0.02379 | `263c725892de3280` | `#l.1-5` | hospital-grade pump built for serious supply work at home. Its Dual-Pump Dual-Control design runs two independent channels so each breast gets its own |
| 3 | `d4ca2374dc720750fe8b` | 0.01961 | `263c725892de3280` | `#l.1-2` | s 17/19/21 mm inserts for a snug fit. The 180 ml collector means fewer interruptions, and Type-C charging takes about 2.5 hours. Motor, Suction, Modes |
| 4 | `08553a709bdbc6f123a9` | 0.01933 | **`None`（空）** | `#素材/recvw7XJiSzmOO/图片素材/#img.1` | [image_ocr] momcozy Boots渠道吸奶器纸托盘陈列设计修改 2026/07/28 momcozy 01-1 Boots渠道吸奶器纸托盘修改 修改要求： 立品背板中有效信息不要被产品遮拦… |
| 5 | `3fdb98df3aa07e5b8549` | 0.01929 | `d45e9b4d54898eee` | `#l.1-46` | —or, BUYING FOR BABY 43 if you’ll be sharing, baby’s corner of your room. Of course you’ll want to fill your baby’s nursery with an eye toward cutenes |

## 第 5 步-3 · 索引覆盖与 registry 声明的已知限制（**原文照抄**）

- **可用单元数**：`kb/l6/registry/l6.json` → `scope.usable_units` = **4261**；`counts.usable` = **4261**；`counts.bm25_indexed` = **4260**（差 1 = 上面那条切不出词元的失败项）；`counts.vector_units_indexed` = **4261**、`vector_segments` = **25874**。闸门复算值一致：`可用单元 复算 4261 ｜ 自报 4261 ｜ 索引 4261 行 ｜ 向量 25874 行 ｜ 倒排 4261 篇 ｜ L2 单元 12213`。
- **默认检索模式**：registry `mode` = **`vector_plus_bm25`**（`retriever.py --mode` 默认 `auto`，本次三条查询实际解析为 `hybrid`）；`fusion.method` = `RRF`、`k` = 60、`rerank` = `本轮不做 rerank 模型`。
- 索引子库：`kb/l6/bm25/{docs,postings_zh,postings_en,meta}.jsonl` + `kb/l6/vectors/{vectors.jsonl,matrix.npy,meta.json}` + `kb/l6/index/l6.jsonl`。

**`retrieval_capability.known_limitations`（8 条，原文照抄，未润色）**：

```
"跨语言只有多语模型的弱对齐：中文查询能拿到英文素材的较高相似度，但不等价于翻译级召回",
"同义改写受限：2019 年的多语 MiniLM（384 维），对行业黑话/新造词的语义区分有限",
"规避型表述（拼音、拆字、谐音、符号分隔、小语种）召回受限：这类本来就绕开字面，向量也未必抓到",
"无重排（本轮不做 rerank 模型），Top-N 只做 RRF 融合，长尾排序质量未校验",
"无命中阈值：检索器一律返回 Top-N，不带相关性阈值，是否采纳由下游判定",
"融合分不能当阈值用：RRF 分只是名次的倒数（Top1 恒为 1/(k+1)=0.016393），A 组与 B 组看起来一样高；真要设阈值得取原始分（BM25 分 / 余弦分），而原始分在 A/B 两组之间仍有重叠（实测 A 组 BM25 最低 5.32 < B 组最高 10.02）",
"超长单元分段后每段独立成向量，段间语义依赖未建模",
"P0 证据单元（321 条）不在向量索引内，只能走 kb/l5/matcher.py"
```

**"覆盖不是全量"的原文（`kb/l6/SCOPE.txt` 头部，节选逐字）**：

```
#       **不在此文件里的可用单元不会进 L6 索引。**
…
# 这不是"少收了知识"，是**拒绝把网页全文当知识**。整页抓取混进 L2 属于口径缺陷，
# 应由 L2/L3 口径侧加尺寸/来源护栏解决（已登记为待办），不该靠 L6 兜。
```

registry 同处的 `scope.scope_file_note` 原文：
```
SCOPE.txt 是人工核定白名单，由 l6_scope_lib.apply_scope_file() 在建索引侧生效；不在此文件里的可用单元**不会**进索引（宁可少收，不可把整页抓取混进来稀释检索）。
```
`no_hit_semantics` 原文：
```
bm25_only: 字面未匹配，不代表合规 / vector_only: 语义未匹配，不代表合规 / hybrid: 字面与语义均未匹配，但仍不代表合规
```

## 附加实测 · 本 RUN 主题（playard）在 L6 里**没有可召回单元**（只读核验，未改任何数据）

三条 playard 查询的 Top-5 **没有一条**是 playard / 游戏床内容（返回的是汽车安全座椅、窒息急救、玩具箱、摇篮、吸奶器、保险等）。为区分"库里没有"与"有但召回没拿到"，做了两步只读核对：

1. 按 `unit_id` 集合比对（**不靠文本 grep**）：`kb/l2/units.jsonl` 中 JSON blob 含 `playard`（大小写不敏感）的单元 **36 条**；这 36 条的 `unit_id` 落在 `kb/l6/bm25/docs.jsonl` 的 **0 条**（doc 的 4261 个 `unit_id` 与 `kb/l2/units.jsonl` 完全同源，重叠 4261/4261，编号口径可比）。
2. 查白名单：这 36 条**没有一条**在 `kb/l6/SCOPE.txt`（4293 条 id）里 ⇒ 它们是被**人工白名单**挡在索引外的，不是建索引失败。

⇒ 结论（**候选口径**）：本 RUN 的主题 playard **在 L6 索引里没有任何可召回单元**，因此这三条查询返回的 Top-5 全是**跨主题邻近候选**，不构成 playard 素材的 L6 证据。这是**范围（SCOPE）事实**，不是召回 bug —— 但意味着本单不能靠 L6 出 playard 结论。
⚠️ 顺带更正一条容易踩的误判：`kb/l6/index/l6.jsonl` 与 `kb/l6/bm25/docs.jsonl` 都**不存全文**（前者只有元字段，后者只有 `text_excerpt` 且 4261 条里 2836 条被截到 160 字）—— 拿文本 grep 这两个文件会得出假阴性；判断"某主题在不在索引里"必须按 `unit_id` 集合比对。

## blockers / 未做到的事（不隐瞒）

- **B1 · 锁竞争导致闸门晚 2 分钟**：库根 `kb/.work/.kb.lock` 被另一会话持有（`{"run_id": "PERF-S2-BASE-01-L6", "pid": 78466, "at": "2026-10-05T10:45:42"}`），编排器按 `lock.held_alive` 正确拒跑（exit 2）。按铁律**未撬锁、未删锁**，等 20 秒重试，**第 6 次成功**（前 5 次均 exit 2）。`ps` 在沙箱内不可用（`/bin/ps: Operation not permitted`），故持有者是否存活只能按锁记录 + 编排器判定，**没有独立复核进程存活**。
- **B2 · `l6_scope.py` exit 1（对账 FAIL，非本次引入）**：原文 `❌ **基准落伍**：l3_stats.json 的 kept=3540 不等于库口径可用数 4261；该基准出自 kb/.work/l3_distill2.py（2026-09-29/30 四处修订一条都没有）⇒ 拿它当边界就是拿旧口径自证旧口径。**本对账判 FAIL，不判 PASS。**` 预演档下它**不写** `kb/.work/l6_scope.json`，所以该 FAIL **只能**靠 `--apply` 消掉 —— 本次禁止写档，**如实留着红**，未加开关绕过。
- **B3 · 落章件 `verdict = FAIL` 的机制**：`kb/.work/l6_report.py:149` 为 `run["verdict"] = "PASS" if (integ["verdict"] == "PASS" and scope["reconcile_ok"]) else "FAIL"`。它读的是**现存的** `kb/.work/l6_scope.json`（mtime 10-05 10:08，`run_id=20260923-1400`、`reconcile_ok=False`）与 `kb/.work/l6_integrity.json`（mtime 10-05 10:12，`run_id=daily-20261005-0957-L6`、`verdict=PASS`）。⇒ 本次 `verdict=FAIL` **完全由那份陈旧的 scope 件决定**（`integrity_verdict` 在落章件里是 `PASS`），不是我这次执行失败，也**不是**闸门失败。预演档下无法刷新它（要 `--apply`）。
- **B4 · `l6_selftest.py` 预演只判了 5/14 条**：原文 `[dry-run] 预演 → kb/l6/runs/RT-20261005-PLAYARD-VIDEO-L6-selftest-dryrun.json（**未写** kb/l6/selftest.json）｜已判断 5/14 条查询`。给出的 A 组数字（`A_all bm25_only hit@3 1.0 p@3 0.8｜vector_only hit@3 0.8 p@3 0.467｜hybrid hit@3 1.0 p@3 0.733`）**只覆盖 A_zh/A_en 5 条**；B 组三模式全为 `None`（`返回结果=False`）。⇒ 这些数字**不得**当成完整 14 条自验结论。
- **B5 · `retriever.py` 人类可读输出在候选缺 `source_sha256` 时崩**：查询 3 打到 rank 4 时 `TypeError: 'NoneType' object is not subscriptable`（`kb/l6/retriever.py:481`，`r['source_sha256'][:16]`），**exit 1**，rank 5 未打印。触发单元 = `08553a709bdbc6f123a9`（`#素材/recvw7XJiSzmOO/图片素材/#img.1`，表 `素材`，`kb_type=internal_sample`），其 `source_sha256` 实为 `null`。同上查询用 `--json` 档 **exit 0**、5 条候选齐全（上表第 3 条即取自 JSON 档）。**未修**（只读档，改代码超出授权）。
- **B6 · 落章件与 `kb/l7/runs/index.jsonl`**：按 `--gate-only` 约定**本次不记账**；`kb/l7/runs/index.jsonl`（1669 行、mtime 10:52）里 **`RT-20261005-PLAYARD-VIDEO-L6` 0 命中**，最后两行是别的会话（`PERF-E2E-01-L7` @10:52:23、`20261005-1052` @10:52:27）。**我没有手工写它**，本次也**没有**带 `--invoked` 的那次记账（不在本层授权内，归父会话）。
- **B7 · 未做（授权外）**：未跑 `l6_bench.py`（★）；未跑 `l6_integrity.py --apply`（完整档 9 项）；未跑带 `--invoked/--skill-session` 的记账；未碰 L7；未改 `kb/l0`–`kb/l7` 任何数据。

## 边界声明

- 全程**只读 / 预演**：**未加** `--apply`、`--write-gate`、`--allow-beyond-policy`（一条都没加）。
- **未修改 `kb/l0`–`kb/l7` 任何数据文件**：以落章件自带的 `artifacts[]` 为准逐件重算 sha256，**15/15 全部 OK（零漂移）**，含 `bm25/docs.jsonl`、`postings_zh|en.jsonl`、`vectors/{vectors.jsonl,matrix.npy,meta.json}`、`index/l6.jsonl`、`registry/l6.json`、`retriever.py`、`selftest.json`、`build_runs.jsonl`，以及 **`benchmark.json`（本次未跑 ★ 引擎，故未变）**。
- 本次会话在库内**只新增/覆盖两个预演产物**：`kb/l6/runs/RT-20261005-PLAYARD-VIDEO-L6-dryrun.json`（落章引擎预演件，任务指定）与 `kb/l6/runs/RT-20261005-PLAYARD-VIDEO-L6-selftest-dryrun.json`（自验预演件，任务指定）；外加 `kb/.work/_rt-l6-gate-RT-20261005-PLAYARD-VIDEO-L6.out`（闸门 stdout 留证）。
- **未手工写 `kb/l7/runs/index.jsonl`**（见 B6）；**未撬锁、未删 `kb/.work/.kb.lock`**（见 B1）。
- 写 `.md` 只用了 `write` 工具；读取 JSON 用了 `/usr/bin/python3 -c`（只读，不落盘），未用 python/perl/sed 写任何文件。
- 本层候选的证据级别**低于 L3 规则 / L5 P0**；上面所有召回一律称「**候选**」，且每条都带 `unit_id`（+ 可用时带 `anchor` 与 `source_sha256`）。**没有把 Top-N 当"命中"**，**没有把「闸门过」说成「索引全对上」**。
