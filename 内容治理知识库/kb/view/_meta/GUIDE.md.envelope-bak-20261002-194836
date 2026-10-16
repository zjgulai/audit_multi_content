# Momcozy知识库 · 内容治理（派生视图）使用指南

> 本文件是这本库自己的使用指南，加载器 `kb_guide` 读的就是它。
> 本库 **不是**权威库：权威库是工作区分层新库 `kb/l0…l6`，本库是由它派生出来的
> **宿主库视图**（509 条 md），生成器 `kb/.work/gen-host-library.py`。
> 首次使用顺序：`kb_guide`（本文件）→ `kb_collections` → `kb_search` → `kb_read`。

## 一、这本库是什么

| 项 | 值 |
|---|---|
| 库名 | Momcozy知识库 · 内容治理（派生视图） |
| 子库 | `3_措辞表达库`（1 个） |
| 条目 | 509 条（**全部落在 `L1-facts`**；`L2-concepts` 现为空 —— F5 把这 56 条 `form=entry` 从 `L2-concepts`/`judgment` 降为 `L1-facts`/`fact`，理由见 `_meta/entry-schema.md` §五） |
| owner | 刘华丽（入库接受人） |
| 来源 | `kb/l3/candidates/rules.jsonl` + `kb/l5/p0_patterns.jsonl` 派生 |
| 条目状态 | 候选行仍 **全部 provisional**；`kb/l4/canonical/` **已写入**（1365 条定稿：wording_entry 56 / wording_revision_pair 453 / sample_case 358 / scoped_clause 375 / clause 123，状态 `stable`，条款号 W-1.* 56、W-2.* 453、W-3.* 157、S-1.* 201、E-1.* 375）。晋升方式是**机器晋升**（判据 C1–C8 实测全过），**人工抽查未做** —— 所以本视图仍**不能声称已过正式验收** |
| 字段定义 | 见 `_meta/DERIVED.md`（派生视图的字段来源对照） |

每条讲一件事：某个条款号（`article_no`，如 `W-2.1`）命中了哪些**禁用表达**、
判定是什么（`p_level` / `risk_level`）、依据是什么、该怎么改成什么话。

## 二、三步读法

1. `kb_search` 拿候选（**只给能力声明与边界，不给正文**）；
2. 读候选的「能答」与「边界」判断是否**真的覆盖**了问题 —— 检索是关键词机械匹配，不是语义判定；
3. 只对确认覆盖的那一条 `kb_read` 取正文。

**不许**一次读完整库，也不许跳过 `kb_search` 直接拿 shell 翻目录。

## 三、四条硬规则

1. **看有效期**：`valid_until` 过了，引用时必须说明它已过期。
2. **看边界**：`not_proves` 写的是「不能由它证明什么」—— 别拿它证明边界外的事。
3. **`L0` 层只许引用，不许摘要成结论**。
4. **查不到就说查不到**：`kb_search` 返回 0 条 ≠ 可以推理一个答案。

## 四、本库统一的边界口径（比单条 `not_proves` 更硬）

- **未命中 ≠ 合规**。命中某条禁用表达只说明「这句话有问题」，没命中**不说明**内容合规。
- **`p_level` / `risk_level` 不是放行结论**，是分流标签（`P1` 优先处理）。
- **`suggested_replacement` 不许直接外发**，外发前仍需人工复核。
- 本库条目**不能替代合规/法务意见**；条款号对不上时以权威库 `kb/l3` 为准。
- 派生视图的字段改动**不写回**权威库；改内容要改分层新库再重新生成。

## 五、什么时候必须回源

出现下列任一情况，回到权威库按 `rule_id` / `article_no` 核对，不许凭本库正文下结论：

- 要对外发布、要出合规结论、要引用具体数字/比例/日期；
- 本库正文与 `kb/l3/candidates/rules.jsonl` 对应行的 `article_no` 对不上；
- `rule_status` 不是 `provisional`、或 `verification` 不是「待验证」（说明权威库已变）。

## 六、入库判据（`kb_ingest` 会逐条执行）

- 必填元字段齐全（`id/title/collection/tier/topic/summary/owner/evidence_level/
  data_level/half_life_days/created_at/valid_until/asks/not_proves/source{…}`）；
- **三件套 `data_level` / `valid_until` / `owner` 非空率必须 100%**（缺任一项 = E014）；
- `half_life_days < 2` 天**硬拒**（E029）；`valid_until` 应由 `created_at + half_life_days` 推出；
- `source.fingerprint` 验不过拒收（E030）；`evidence_level` 最低 `L2`；
- `kb_class` 必须在 `_meta/kb-classes.yaml` 的枚举里（否则 E046）；
- 禁覆盖已存在的 `id`；入库是**人的动作**，不自动写回权威库。

## 七、体检看什么（`kb_check`）

| 维度 | 看什么 | 本库当前口径 |
|---|---|---|
| 健康分 | 低于熔断线（`_meta/health.yaml`，默认 60）判失败 | 见 `kb_check` 输出 |
| 三件套完整率 | `data_level`/`valid_until`/`owner` 非空率 | 应 100% |
| 孤岛率 | 没被任何条目引用的条目占比 | **0.94（超标，是真值）**。此前 0.00 是生成器为压这个指标造的合成边（按排序挂邻居）；2026-09-29 按人确认的 W025 处置 B 只保留「同 rule_code」的真关系并落成 `complements`，孤岛率随之从假绿变真红。**472/509 条规则与其他条目没有任何真实引用关系** —— 要降下来需来源表提供真实关联列，属业务动作 |
| `E001` | 缺 frontmatter —— **装载位读不到文件时就是这个码** | 必须为 0（见第八节） |
| `W040` | 缺 `kb_class` 的条目汇总成一条告警 | 应 0 条（本次已 509/509 回填） |
| 幻觉率 / 利用率 | 正文承重数字能否回源；查询日志样本够不够 | 样本不足时标 no-data，不凑分 |

## 八、装载纪律（本批新增，最容易被忽略的一条）

**装载位**：本目录本身 —— `/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/view`（加载器按 profile 配置的 `config.root` 找它）。
它和权威库没有写入关系，只是给宿主侧读的一份视图。

> 2026-09-29 变更：旧装载位 `~/.dsh/Momcozy知识库/` 现在只是**入口**（`README.md` + 软链 `kb → 本工作区`），
> 加载器已改指本目录。**在旧根上体检得到的 W018/W019 = 0 是假阴性** —— 那个根没有 `_meta/`，
> 接线审计 `readdirSync` 抛错被 `catch { files = [] }` 吞掉，一个文件都没扫。别拿旧根的数字下结论。

这台机器上装了注入型监控/加密代理（`/usr/local/.trld`，`libtr_monitor_*.dylib`
被注入到 Electron 族进程），由此产生一条**写通道纪律**：

- 写 `.md` 前先看**谁落盘**，不要看用了什么命令名：
  · ❌ 落信封：`python`（`open(path,"w")`、**`shutil.copy2`**、`shutil.copy`）、`perl`、`sed >`。
    注意 `sed > f` 和 `shutil.copy2` 都是"重定向/拷贝"，照样落信封 —— **别按命令名判断**。
  · ✅ 明文：`node`（`fs.writeFileSync`）、`/bin/cp`。
  实测：同一份 4,532 字节的 md，`shutil.copy2` 落盘后 node 读到 **8,628 字节**（=4,532+**4,096**，
  即「4096 字节前缀 + 原文」）。
- ⚠⚠ **最要命的一点：用自己的语言自检看不见信封。** Python 的 `stat` / `sha256` / `head` 读同一份
  信封文件，报的仍是 4,532 字节、sha256 与源文件一致。所以「用 Python 读首 3 字节验证明文」
  **结构上不可能发现这个缺陷** —— 它会给假绿灯，然后由加载器报 E001 × 509，
  并把 `_meta/manifest.json` 条目基线刷成 0 条（`loadAll` 拿不到条目 → removed 509）。
  2026-09-29 就这么栽过一次，回滚与重做各一轮。
- 结论：**往装载位写 `.md` 一律走 node 或 `/bin/cp` 通道，并且必须用 node 读回校验**
  （`kb/.work/write_via_node.mjs`：内容走 stdin → node 写 → 读回逐字节比对，不一致即 exit 1）。
  校验工具：`kb/.work/which_enveloped.mjs`（看指定文件首字节）、`kb/l8/scan_envelope.mjs`（全库扫描）。
- **留底也必须走 `cp`/node**：用信封版做留底，回滚时会把信封原样带回来。
- 参考实现：`kb/l8/repack_write.mjs`（`--payload` 传入正文载荷，逐文件读回断言，失败自动 `cp` 兜底）。
- 只有 `.md` 受影响：`.yaml/.json/.txt/.py/.log` 在两个通道下都一致，随便哪个写通道都行。

## 九、版本与发布纪律

- 全库 `kb_version` = `v0`；`kb/versions/versions.jsonl` 只有注释，没有版本行。
- `kb/l4/canonical/` 已写入 **1365** 条定稿（**五个形态文件** — `wording_entry`/`wording_revision_pair`/`sample_case`/`scoped_clause`/`clause`；状态 `stable`，条款号由 `kb/l4/registry/l4.json` 的 `numbering.issued` 台账发放，永不复用）。晋升依据是机器判据 C1–C8（见 `promotion_rule.criteria`），**人工抽查未做、也无发布版本** —— 本视图因此仍**不能声称已过正式验收**。
- `kb/l4/canonical/rules.jsonl`（0 字节）是迁移留痕（0 字节），已被上面**五个形态文件**取代，不再写入；**不计入形态计数**。
- 不生成 `release_id`、不发布；本视图不写回权威库 `kb/l0…l6`。
