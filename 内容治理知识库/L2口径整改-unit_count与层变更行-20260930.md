# L2 口径整改单 · unit_count 与层变更行

> 走的成员：`kb-ingest-extractor`（L1 抽取 / L2 切分 owner）
> 库根：`kb/`（含 `kb/KB-ROOT.json`，权威分层新库）
> 状态：**闸门挂了两条说明项已关掉**；数据台账**一个字节没改**。

---

## 一、为什么动这个（不是没事找事）

本 skill 第 3 条红线原文：**「unit_count 的口径还没写死 …… 改口径要落到 `kb/l2/registry/l2.json`，别在会话里口头约定。」**

`l7/scripts/l2_gate.py` 两个 run 以来一直在说明项里挂着同一句话：

```
N3 口径歧义：最新 split 行 106 不符 ｜ split 行求和 2 不符 ｜ 全行求和 306 不符
  → 要 L2 层主在 l2.json 写明 unit_count 口径
N4 非资源行 1 行（**口径待裁**，不是红）→ 要人做什么：确认它是不是层引擎有意的变更记录；
  若是，把约定写进 l2.json
```

两条都是**指名要 L2 层主（本 skill）做的事**。口径不写死，`l8/l2_resume_guard.py` 的 G 系列判据也用不了 —— 它的注释第 ③ 条写得很直白：「unit_count 口径未定（N3）→ 台账行数与实际单元数本来就对不齐，**不能用行数差判健康**」。

---

## 二、口径定死成什么（结论）

| 行类型 | `unit_count` 的含义 | 依据 |
|---|---|---|
| `split` | **该次 split 执行追加到 `units.jsonl` 的单元行数**（那一批的大小） | `l8/l2_split_run.py:123-130`（`byres[rid] += 1` → `"unit_count": n`）、`recrawl_all_urls.py:325-337`、`recrawl_jsnoise_urls.py:176-186` 三处产出侧代码同义 |
| `invalidated` | **镜像值** —— 等于被它作废的那一批在上一行 split 里记的数，不是本次退役行数、更不是本次新增 | `recrawl_jsnoise_urls.py:150-154`（`len(olds)`） |
| `skipped` | 恒为 0 | 不切的资源没有产物 |

**账实等式（唯一可算的那条）**：

```
units.jsonl 中该资源行数  ==  Σ(该资源全部 split 行的 unit_count)
```

**为什么是「求和」不是「取最后一批」**：`units.jsonl` 是 append-only（旧单元行不删；`retired_units.jsonl` 是**另一份**退役登记，不从这里减行），所以「这个资源现在共有几行」只能是历次追加量的累加。

---

## 三、实测（本轮现跑，不是引用旧结论）

| 口径 | 不符资源数 | 采用？ |
|---|---|---|
| 只取最后一条 split 行 | **106** / 1626 | ❌ 漏计此前的批 —— 106 个不符**全部**是「有 2 条以上 split 行」的资源，恰好证明单位是「批」不是「全量」 |
| **Σ 全部 split 行** | **2** / 1626 | ✅ **本层采用** |
| Σ 全部行（含 invalidated） | **306** / 1626 | ❌ 把退役的批数了两遍 —— 306 恰好等于闸门 N1「被作废后仍留产物」的资源数，两者同源 |

**全库级残差也归了因**：

```
Σ(全库 split 行 unit_count) = 12179
units.jsonl 行数             = 12158
差                            =    21  ← 不是未知缺口
```

21 正是 `kb/l2/runs/20260930-0030-dedup.json` 记的 `dropped_rows`（同一 `unit_id` 被写两次）。独立复核：在留底件 `kb/l2/_archive/units.jsonl.before-dedup-20260930-0030` 上按 `unit_id` 统计，重复 id **恰好 21 个**、应丢 **恰好 21 行**，且这 21 行**全部**落在那 2 个偏差资源上。

**那 2 条偏差是什么**（已逐条挂账，不是丢数）：

| 资源 | 产物行数 | Σsplit | 台账行序 |
|---|---|---|---|
| `…feishu.cn_wiki_AD26wCxzsiyJzUkqREgcg0X8nDd` | 12 | 24 | `skipped(0)` → `split(12)` → `invalidated(12)` → `split(12)` |
| `…feishu.cn_wiki_Cliyw2MGtipp2MkDamrctDKNnsI` | 9 | 18 | `skipped(0)` → `split(9)` → `invalidated(9)` → `split(9)` |

同一个 sha 在一个 run 内被「作废一次 + 重切一次」，台账重复记了一条 split；产出逐字相同 → `unit_id` 也相同 → 同一批单元被写了两份（留底件里实测 24 行 = 12×2、18 行 = 9×2）。**双写行已由 `l8/l2_dedup_units.py` 压掉并留底，`unit_id` 一个没少。**

---

## 四、N4 那行是什么

`manifest_l2.jsonl` 第 1456 行：

```json
{"change": "add_field_rule_eligible", "layer": "l2", "run_id": "20260924-1240",
 "units": 9469, "true": 9468, "false": 1, "none": 0,
 "text_sha_before": "271b13ba…", "text_sha_after": "271b13ba…"}
```

判定：**是引擎有意的「层变更记录行」，保留不删。** 两条依据：

1. `text_sha_before == text_sha_after` —— 那次迁移**没碰正文**，只加了 `rule_eligible` 字段；
2. 同一事实已在本 registry 的 `rule_eligible_inheritance` 落档（`coverage 9469` / `none 0`）—— **同源互证**，不是重复登记。

它不是资源行（没有 `resource_id`），本就不该进资源级判据；现在有了明文约定，闸门不再报「口径待裁」。

---

## 五、改了什么 / 没改什么

**改了（3 个文件，均在 L2 写档白名单内）**

| 文件 | 改动 |
|---|---|
| `kb/l2/registry/l2.json` | 新增 `unit_count_semantics`（口径 + 实测 + 2 条偏差 + 全库残差归因）、`manifest_change_rows`（层变更行约定）、`accounting_rule_verdict`（原式不可计算，连同改判依据）；`accounting_rule` 改为对象并标明「作废、保留原文供追溯」；`changes[]` 追加 `20260930-1440` 一条 |
| `kb/l7/scripts/l2_gate.py` | 改读 registry 口径：N3 从「报歧义」改为「按已声明口径逐条点名不符项」，未登记的偏差会单独告警；N4 按约定认领层变更行。registry 读不到时**退回定死前的行为**（不崩） |
| `kb/l7/registry/layers.yaml` | L2 层契约的 `gate` 描述同步（原文说「口径歧义……单列说明项」，现已不成立） |

**没改（红线 2：台账 append-only）**

`units.jsonl`、`manifest_l2.jsonl`、`index/l2.jsonl`、`manifest_l1.jsonl` **逐字节未动**，改前改后 sha256 相同：

```
de434fb39501f34f031732c316953a9fc9ccdad6132258a592985cf3dd73f631  kb/l2/units.jsonl
7b0b64f9fdbd75593feaf6948409bbf58d59d157674db1453ef5aec39e1f3f3e  kb/l2/manifest_l2.jsonl
```

**一条台账行都没删**（那 2 条偏差是**挂账**，不是清零）。留底：`kb/l2/registry/_backups/l2.json.before-unit_count-convention-20260930-1440`、`kb/l7/_backups/l2gate-20260930-1440/l2_gate.py`、`kb/l7/_backups/layers.yaml.before-l2-unit-count-contract-20260930-1445`。

---

## 六、验收（本轮实测）

| # | 判据 | 实测 |
|---|---|---|
| A1 | `l7/scripts/l2_gate.py` 退出 0 | ✅ 五项判据 **0 违规**；N3 报「不符 2 个资源 ｜ 其中**已在 registry 登记的偏差 2 条**」；N4 报「已按约定认领」 |
| A2 | L2 预演 +N == 落盘 +N | ✅ 预演 **+0**，无落盘动作（不改数据即自洽） |
| A3 | 再预演 +0（幂等收敛） | ✅ `待判 31 → 元数据闭合 31 / 补切 0`，`+0 行` |
| A4 | `l1_gate.py` 仍过 | ✅ 退出 0（全部缓存可复用） |
| 附加 | `layers_check.py` 层契约自检 | ✅ 六类问题合计 0 |
| 附加 | 改后文件无信封态 | ✅ registry 仍是合法 JSON（首字节 `{`）、闸门仍能编译运行 —— 信封式前缀会破坏 JSON 解析，故「能解析」即为无信封的证明 |

**反测**（在 `/tmp` 夹具上，不碰真库）：registry 缺失 → 退回旧行为且不崩；声明了口径但偏差未登记 → 报「未登记的偏差 1 个」；登记后 → 报「已登记 1 条」。

> ⚠️ 本机**没有 node**（`scan_envelope.mjs` 无法运行），所以信封检查用的是「JSON 可解析 / 源码可编译」这条通道无关的证明，不是 node 读回比对。本次只写了 `.json`/`.yaml`/`.py` —— 按库指南只有 `.md` 会被落信封。

---

## 七、仍然开着的事（不替下一个人拍板）

1. **滞后 311 个资源未切分**（`internal_sample` 304 / `wording` 7）—— 闸门 N2 仍报。这不是本轮范围：引擎预演已 `+0`（缺口口径「没有当前正文的单元」判定它们**不该切**），而闸门 N2 看的是「台账有没有 split/skipped 结论」，两个口径不同源。要闭合得先定「这 304 条内部样本要不要进 L2」。
2. **两份待补件单仍未开工**（都缺同一样东西 —— 源侧输入，不是缺工具）：
   - `抽取交接-S12Pro-listing正文-待补record_id.md`：正文抽得出、锚点闭合不了（缺 表名 + `record_id` + 字段名）；
   - `条款抽取-政策文本切分与蒸馏-待补源文本.md`：政策文本本体没到（A1 粘贴 / A2 本地路径 / A3 链接三选一）。
3. **`kb/l7/scripts/_backups` 是个文件不是目录**（内容是 `l2_gate.py` 的一份副本，像是某次 `cp` 参数写反留下的）。本次没动它 —— 它不在任何闸门的判据里，但名字会误导后来者。

---

## 八、这条不能证明什么（`not_proves`）

- **不能证明 L2 账实已经完全对齐**：残差 21 是**已归因**，不是已消除；台账是 append-only，历史重复行不回收。
- **不能证明那 304 条滞后资源「没有内容」**：闸门口径判定的是「按现行切分器不该切」，不等于「原文没知识」。
- **不能证明 unit_count 口径在**别的**写入者上也成立**：本口径取自三处产出侧代码（`l2_split_run` / 两本 recrawl）的实测语义；将来若新增写 `manifest_l2` 的脚本，须按同一约定写，否则本口径即失效。
- **不能作为合规结论**：本层只做「素材 → 知识单元」，不做三态判定。
