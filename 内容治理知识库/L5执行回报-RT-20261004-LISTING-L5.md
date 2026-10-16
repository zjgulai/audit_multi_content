# L5（P0 判定层）执行回报 · RUN = RT-20261004-LISTING-L5

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**查询档 / 预演档**（不满足写档三条件的第 ③ 条「人开闸」⇒ 全程无 `--apply`）
- 待审内容：`吸奶器静音设计，夜里不吵醒宝宝，续航 8 小时`
- 本次只跑 L5。**不写库、不跑 l5_bench.py、不跑别的层、不跑 kb_pipeline.py、不出三态结论。**

## 1. skill 加载

用 `skill` 工具加载 **`kb-p0-check`** —— 正文已进上下文（不是「知道归它管」）：
查询档只读、不调 `l5_prep.py`/`l5_export.py`、不改 P0 模式表；引擎清单读 `layers.yaml` 本层 `engine`（唯一真源）；
并按它 §2 红线执行（未命中 ≠ 合规；不自己造模式；不给三态结论；引用须带 anchor + authority + unit_id + source_sha256）。

## 2. 执行的命令（逐条，带退出码）

| 序 | 命令 | 退出码 | 关键输出 |
|---|---|---|---|
| ① | `sh kb/kbpy .work/l5_prep.py RT-20261004-LISTING-L5` | **0** | `[dry-run] l5_prep.py 未落盘`；自报会**追加写** `kb/l3/candidates/rules.jsonl`、`manifest_l3.jsonl` |
| ② | `sh kb/kbpy .work/l5_export.py RT-20261004-LISTING-L5` | **0** | `[dry-run] l5_export.py 未落盘`；自报会**覆盖写** `p0_patterns.jsonl`、`l5/index/l5.jsonl`、`registry/l5.json` |
| ③ | `kbpy .work/l5_bench.py` | **未跑** | 按 `layers.yaml:419` 登记跳过（无预演档，`:121` 无条件写 `benchmark.json`，不解析 argv）。旁证：`benchmark.json` mtime 仍 `Oct 3 06:56` |
| ④ | `kbpy .work/l5_report.py …` | **未跑** | 台账已由主会话以本 RUN 生成；**同 RUN 重跑会覆盖该台账**，按指令「读即可」只读取 |
| ⑤ | `sh kb/kbpy l5/matcher.py --text "吸奶器静音设计，夜里不吵醒宝宝，续航 8 小时"` | **0** | `结论: PASS ｜ 耗时 138.36 ms ｜ 文本 23 字符` |
| ⑥ | 同上 + `--json` | **0** | `{"elapsed_ms": 25.88, "hits": []}` |
| ⑦ | `sh kb/kbpy l5/matcher.py --selftest` | **0** | `载入 P0 模式 7 条`；**9 正例全命中 / 5 负例零误报** |
| ⑧ | 阳性对照 `--text "采用无痛设计，缓解疼痛，帮助催奶增产。"` | **1** | `结论: BLOCK`，H02 + H07 各命中 4 处 ⇒ 证明该命令形式**确实会命中** |
| ⑨ | 阴性对照 `--text "这款吸奶器静音，夜里不吵醒宝宝"` | **0** | `结论: PASS`（无命中） |
| ⑩ | `sh kb/kbpy l7/scripts/l5_gate.py` | **0** | 实质 4 项全 PASS、基线 2 项 FAIL（已登记）；`结论：✅ 过` |

★ matcher 的 `PASS` / `BLOCK` 是它自己的档位词（`match_note_enum: ["BLOCK"]`，退出码 0=无命中 / 1=命中），
**不是审查三态结论** —— 我不据此出「能不能发」。按 skill 红线：**未命中 ≠ 合规**。

零写复核：5 个被跟踪件跑前跑后 sha256 `sha256sum -c` 全 **OK**
（`p0_patterns.jsonl` / `index/l5.jsonl` / `registry/l5.json` / `l3/candidates/rules.jsonl` / 本 RUN 台账）。
唯一被写的是闸门自检器自己的证据文件 `kb/.work/l5_integrity.json`（闸门自述「不是层产物」）。

## 3. matcher 命中了哪些 P0 模式

## **0 命中**（`hits: []`，7 条模式全未命中）

不是「matcher 坏了」：⑧ 阳性对照在同一命令形式下命中并返回退出码 1，⑨ 阴性对照一致，⑦ 自测 9/5 通过。

模式表现存 7 条（`kb/l5/p0_patterns.jsonl`，`pattern_count=7`，全部 `p_level=P0` / `type=keyword`）：

| rule_code | pattern_id | authority | 命中表达数（keyword/regex） |
|---|---|---|---|
| H02 增产/催奶 | `p-755f9ff377c3052c` | expert | 24 / — |
| H04 专家推荐 | `p-521d9d1502ee0bfa` | expert | 13 / — |
| H05 绝对安全 | `p-08487282e2d400fe` | expert | 13 / — |
| H06 FDA | `p-485c67cc9af960bf` | **inferred**（按码白名单准入） | 5 / — |
| H07 无痛/缓解疼痛 | `p-964b3c2e22b48ade` | expert | 17 / — |
| H09 模仿婴儿吸吮 | `p-d31dfbc932cb84ac` | expert | 8 / — |
| U04 疼痛症状词 | `p-4d1fe41caef6e3b1` | expert | 4 / — |

**两点必须说清（否则「0 命中」最容易被误读）：**

1. **模式表里没有条款号字段**（`article_no` / `clause_no` 实测 0 命中）—— L5 的命中项带的是
   `pattern_id` + `rule_id` + `anchor` + `authority` + `evidence_units[].unit_id/source_sha256`；
   **条款号在 L4**，不在本层产出范围。所以本轮不存在「命中词 / 条款号」可列。
2. **「静音」在模式表里出现过，但只是散文、不是可执行模式**：该词 2 次出现，**都在 H02/H07 的
   `suggested_replacement` 里**（原文：「静音表述改客观参数(as low as 48 dB),避免 whisper/silent/ultra-quiet 绝对化」），
   **不在任何 `match_terms` / `regex_patterns` 里** ⇒ matcher 不命中是**正确的**。
   按 skill 红线「**不自己造模式**」，**不许**把这段建议改法升格成一条 P0。
   待审文本其余实词在模式表里也都是 0 次：`吸奶器` 0、`吵醒` 0、`续航` 0。

## 4. 闸门：实质项 / 基线项分别红在哪

**实质 4 项 —— 全 PASS（无红）**：`pattern_traceability` / `no_fabricated_words` / `version_discipline` / `offline`
（另有闸门自带一项 `C_p0_count_recomputable`：PASS，导出 7 条 == 复算 7 条）。

**基线 2 项 —— 都 FAIL，且都已在 `kb/l7/registry/l5-known-drift.yaml` 逐项登记**（闸门据此不判红，退出码 0）：

- **`frozen_layers` FAIL**：判据要求 l0/l1/l2 内容指纹与 mtime **等于** l5 首次写入 `2026-09-23 13:22:33` 那一刻；
  实测 l0 max_mtime `2026-10-03 23:56:55`、l1 `23:59:32`、l2 `2026-10-04 00:00:45`
  ⇒ 日更活库上**恒 FAIL**。登记成立。
- **`l3_append_only` FAIL**：账本自证两条硬编码子条件**都不成立**：
  - (a) `byte_identical_to_pre_append: false` —— 前 509 行 sha `acf77a6a0b05937d` ≠ prep 记的 `743dc62398311b02`。
    我独立复算：`wc -l` = **1018**，且**整 1018 行**的 sha256 = `743dc623…`（与 `l5_prep.json.before_sha256` 完全一致）
    ⇒ 判据是拿「前 509 行」去比「整 1018 行」，文件已是 1018 行时**恒不等**。
  - (b) 判据要求 `appended_distiller_version == ["l3-0.2"]`；实测 `by_version = {"None": 1018}`，
    且 `rules.jsonl` **0 行**含 `distiller_version` / `rule_kind` 键（富化按设计落在 `manifest_l3.jsonl`，其中 `l3-0.2` 11707 行）
    ⇒ 该子条件在活库上**恒假**。
  - 结构条件其实**成立**：`appended_covers_baseline: true`、`baseline_ids_unique: true`，我独立复核「追加段 rule_id 集合 == 基线集合」为 **True**。
    即：**不是数据坏了，是判据写在过去的时点** —— 分类为「判据过期」成立。

**别粉饰的一句**：落章台账 `kb/l5/runs/RT-20261004-LISTING-L5-dryrun.json` 的顶层 `verdict` 是 **`FAIL`**。
它由基线两项传染而来（`l5_report.py` 的 verdict = integrity ∧ benchmark ∧ selftest ∧ spot，
而后三者分别为 FAIL/PASS/PASS）—— **这个 FAIL 不代表实质红**，读的时候别当成第 3 个实质红。

## 5. 有没有「新出现的红」

**没有新出现的实质红。** 本 RUN 台账的 `integrity` / `benchmark` / `selftest` / `patterns` / `selection` / `precondition_a/b`
与上一次 L5 跑（`PIPE-20261003-2354-L5-dryrun.json`）**逐键相同**（benchmark=PASS、selftest=PASS、B0 模式表与 selection 口径未变）。

但有三条**如实列出**的状态/漂移，按严重度排：

1. **（新状态，但当前不算红）本 RUN 的旧模式表归档件缺席。**
   `kb/l5/runs/RT-20261004-LISTING-L5.p0_patterns.superseded.jsonl` 实测**不存在**，台账 `artifacts` 自报 `missing: true`；
   上一次 RUN 的同名件存在（93848 字节，sha `470e3fba…` = 当前模式表 sha）。
   本 RUN 是预演（`applied: false`，没覆盖写）⇒ 现在不构成红；**但一旦对本 RUN 加 `--apply`，就踩
   `layers.yaml` L5 那条「旧模式表必须**人工**归档」的红线（归档动作不在脚本里）。** 有写档意图前必须先补。
2. **（登记文本 vs 活库漂移，不改变闸门结论）** `l5-known-drift.yaml` 里 `l3_append_only` 的
   `why_stale` / `evidence` 写的是「实测当前文件**正好 509 行**」「前 509 行前缀哈希与 `l5_prep.json` 的
   `before_sha256` **逐字节一致**」—— 实测当前 **1018 行**、两个哈希**不相等**。
   闸门是按**条目名**（`BASELINE_ITEMS` + `stale_criteria` 名单）命中的，所以 exit 0 不受影响；
   但该登记的证据段已过期、经不起复核，建议主会话更新判据或重写证据段。
3. **（文档计数不准，不是红）**：
   - skill playbook 写「实测 21 条 P0 → 入选 **6** 条」，活库是 **7** 条（H06 按码白名单准入 1 条，与 `registry/l5.json.excluded` 自洽：6+1+8+6=21）。
   - 先例文档《文案判定-轻音设计夜间不吵醒宝宝-20260930.md》写「**10** 正例全命中」，实测 selftest 是 **9** 正例 / 5 负例；
     该文档记录的 `matcher.py` sha `4197b474…` 与当前**相同** ⇒ 代码未变，是先例文档计数不准。

**与先例的一致性（说明 0 命中不是回归）**：同一先例文档记录当时同法调用
`matcher.py --text "轻音设计，夜间吸乳不吵醒宝宝。" --json` → `{"hits": []}`（7 条全未命中），
与本次一致。本次 0 命中**既不是新红、也不是回归**。

## 6. 我不会做的事（边界）

- 没加 `--apply`；没跑 `l5_bench.py`；没跑别的层；没跑 `kb_pipeline.py`。
- 没改 `kb/` 下任何数据文件；没重新生成别的 `run_id`；没重跑 `l5_report.py`（避免覆盖主会话台账）。
- **没给三态结论**（能不能发 / PASS-REVIEW-BLOCK 属 `kb-review` 与判定主体，不属本层）。
  本次「0 命中」只说明**不是最高优先级**，其余风险仍要走评审链。
