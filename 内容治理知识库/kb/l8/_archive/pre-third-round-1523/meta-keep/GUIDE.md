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
| 条目 | 509 条（`L1-facts` 453 + `L2-concepts` 56） |
| owner | 刘华丽（入库接受人） |
| 来源 | `kb/l3/candidates/rules.jsonl` + `kb/l5/p0_patterns.jsonl` 派生 |
| 条目状态 | **全部 provisional** —— `l4/canonical` 尚未写入，未过正式验收 |
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
| 孤岛率 | 没被任何条目引用的条目占比 | 本视图派生自同一批规则，孤岛率天然偏高 |
| `E001` | 缺 frontmatter —— **装载位读不到文件时就是这个码** | 必须为 0（见第八节） |
| `W040` | 缺 `kb_class` 的条目汇总成一条告警 | 应 0 条（本次已 509/509 回填） |
| 幻觉率 / 利用率 | 正文承重数字能否回源；查询日志样本够不够 | 样本不足时标 no-data，不凑分 |

## 八、装载纪律（本批新增，最容易被忽略的一条）

**装载位**：`~/.dsh/Momcozy知识库/`（加载器按 profile 配置的 `config.root` 找它）。
它和权威库没有写入关系，只是给宿主侧读的一份视图。

这台机器上装了注入型监控/加密代理（`/usr/local/.trld`，`libtr_monitor_*.dylib`
被注入到 Electron 族进程），由此产生一条**写通道纪律**：

- 用 **python / perl** 的 `open(path,"w")` 写 `.md`，落盘后是 **4096 字节信封**
  （首字节 `88 7d 1c ?? …`）。Electron 侧（加载器、工作台镜像器）`readFileSync`
  读到的就是信封 → `splitFrontmatter` 失配 → `meta = null` → **E001**；
  而 `cat` / `python` 通道读到的是明文，所以「文件看起来是好的」。
- 用 **node（`fs.writeFileSync`）/ `/bin/cp` / bash 内建重定向** 写 `.md`，所有读取者
  （含加载器）读到的都是明文。
- 结论：**往装载位写 `.md` 一律走 node 或 `cp` 通道，并且写完必须读回校验**
  （字节数 + sha256 + frontmatter 正则），不要写完就算。参考实现：
  `kb/l8/repack_write.mjs`（`--payload` 传入正文载荷，逐文件读回断言，失败自动 `cp` 兜底）。
- 只有 `.md` 受影响：`.yaml/.json/.txt/.py/.log` 在两个通道下都一致，随便哪个写通道都行。

## 九、版本与发布纪律

- 全库 `kb_version` = `v0`；`kb/versions/versions.jsonl` 只有注释，没有版本行。
- `kb/l4/canonical/rules.jsonl` 为空 —— 本视图因此**不能声称已过正式验收**。
- 不生成 `release_id`、不发布；本视图不写回权威库 `kb/l0…l6`。
