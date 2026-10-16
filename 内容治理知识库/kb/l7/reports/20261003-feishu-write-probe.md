# 2026-10-03 飞书写入探测报告（第一次实测）

**目的**：把「评审链结论能否写进飞书」从**没实测**变成**实测过**。
**结论**：✅ **写通道打通** —— 云文档（正文）＋ 登记在案的多维表格（结论行）**都写入成功并读回一致**。
⚠️ 本件是**探测记录**，产物带 `PROBE` / `可删` 标记，**不是真实送审**。

## 一、写了什么对象

| 对象 | 标识 | 位置 |
|---|---|---|
| 云文档（报告正文） | `document_id = RqqQdUBlWoyd11x2JhOcl8vRnCc`（rev 3） | https://momcozy-in.feishu.cn/docx/RqqQdUBlWoyd11x2JhOcl8vRnCc |
| 多维表格行（结论） | `record_id = recvwWsxSaZcIJ` | base `RY2UbCRjXaeeWwscUPScVN5AnQc` ／ table `tblCXPQVzfFWWCon` ／ 内容 ID `PROBE-20261003-FEISHU-WRITE` |

身份：`--profile dsh-kb`（app `cli_aa2243de0438dcd7` = `conclusion-destination.yaml` 登记的「守衡」）／ `--as bot`。

## 二、写入用的命令（照抄可复跑）

```bash
export PATH="$HOME/.dsh/bin:$PATH"          # lark-cli 在 ~/.dsh/bin，不在默认 PATH

# ① 建云文档（正文走 @file，markdown）
lark-cli --profile dsh-kb docs +create \
  --title "【探测】内容审查报告 rv-20261003-082840（可删）" \
  --content @/tmp/probe-report.md --doc-format markdown --as bot

# ② 写多维表格行（★ 形状：字段平铺，select 传数组）
lark-cli --profile dsh-kb base +record-batch-create \
  --base-token RY2UbCRjXaeeWwscUPScVN5AnQc --table-id tblCXPQVzfFWWCon \
  --json '{"create_records":[{"内容 ID":"PROBE-…","状态":["BLOCK"], …}]}' --as bot
# → {"record_id_list": ["recvwWsxSaZcIJ"]}

# ③ 读回验证
lark-cli --profile dsh-kb base +record-get --base-token … --table-id … --record-id recvwWsxSaZcIJ --as bot
lark-cli --profile dsh-kb docs +fetch --doc RqqQdUBlWoyd11x2JhOcl8vRnCc --as bot
```

## 三、读回证据（关键字段）

行（`+record-get` 输出，节选）：
```
- `内容 ID`: PROBE-20261003-FEISHU-WRITE
- `Agent 结论`: BLOCK          - `问题数量`: 7        - `置信度`: 0.97
- `状态`: ["BLOCK"]            - `报告链接`: https://momcozy-in.feishu.cn/docx/RqqQdUBlWoyd11x2JhOcl8vRnCc
- `问题分类汇总`: 功效宣称-疼痛功效承诺 2；绝对化与安全承诺-虚假安全承诺 1；背书与资质-医生专家推荐 1；
                 背书与资质-监管认证宣称 1；背书与资质-医疗场景宣称 1；背书与资质-等级与资质背书 1
- `渠道`/`产品线`/`送审版本`/`内容类型`/`复核结论`：均与写入一致
```
文档（`+fetch`）：标题 + 7 条完整清单（含条款号 W-1.53 / W-1.33 / W-1.13 / W-1.8 / W-1.6 / W-1.35 / W-1.11、
anchor、source_sha256）＋分类汇总表 ＋复现命令，**逐字一致**。

## 四、这次踩到的坑（下一个人别再踩）

1. **`--json` 不是 bitable 原生形状**：正确是 `{"create_records":[{"<字段名>": <值>, …}]}` ——
   **字段平铺在记录对象上**，不是 `{"records":[{"fields":{…}}]}`；**select 字段传数组**（`"状态":["BLOCK"]`）。
2. **命令名带 `+`**：`+record-batch-create` / `+record-get` / `+record-batch-update`；`record-create` 不存在。
3. **`docs +fetch` 用 `--doc`**，不是 `--document-id`。
4. **`lark-cli` 不在默认 PATH**（在 `~/.dsh/bin/lark-cli`）；且**默认 app 不是 `dsh-kb`**
   （默认是 `cli_aa2e11d952f85be9`）—— 写登记表**必须** `--profile dsh-kb`，否则按登记的授权关系大概率写不进。
5. **本条链路是「评审链之外的动作」**：KB 侧 `review-engine/core/feishu_adapter.py` 的定位是
   `Feishu-neutral mapping with a local JSON fallback`（`transport_status: json_fallback_pending_feishu_credentials`），
   **KB 链条本身不写飞书** —— 写飞书这次是**手工按登记件执行**的。

## 五、没验到的（别当成已通）

- **没有**任何脚本把「评审 → 建文档 → 回填链接」串起来：本次是一次性手工编排，**未入 skill、未入引擎**。
- **未**验证 user 身份写入（本次全程 bot）；**未**验证 30 天留存；**未**验证机器人被移出协作者后的行为。
- **未**验证并发写（同一 base 并发可能撞 `1254291`）。

## 六、清理（一条命令，随时可跑）

```bash
export PATH="$HOME/.dsh/bin:$PATH"
# 删行（high-risk-write，需 --yes）
lark-cli --profile dsh-kb base +record-delete \
  --base-token RY2UbCRjXaeeWwscUPScVN5AnQc --table-id tblCXPQVzfFWWCon \
  --record-id recvwWsxSaZcIJ --yes --as bot
# 删文档（drive +delete；<type> 与 token 见 --help）
lark-cli --profile dsh-kb drive +delete --file-token RqqQdUBlWoyd11x2JhOcl8vRnCc --type docx --as bot
```

---
> 本件只记录实测过程与证据；结论字段全部照抄 CLI 输出，未改写。

## 七、正式流程化（同日第二批）

链路已固化成 **一个脚本 + 一份登记**，不再是手工编排：

- 脚本：`kb/l7/review-engine/core/feishu_publish.py`（**默认预演**；`--apply` 才写）
- 去向：仍从 `kb/l7/registry/conclusion-destination.yaml` **现读**（该件新增 `publisher` / `write_modes` /
  `row_idempotency` / `refuses` / `verified_at`）
- 契约登记：`report-output-contract.yaml → applied_20261003.feishu_publish`
- 正文接线：`飞书审查流转/SKILL.md`（源 + 装位）新增「Review → Feishu, wired (2026-10-03)」整节；
  `kb-review §6` 交接件补发布件；`~/.dsh/AGENTS.md` 报告落点补一条

**「从最顶格第 1 行写」的实现与实测**：

- **不传** `docs +create --title`：实测 A/B 两版 —— 传了会得到 `<title>X</title><h1>标题</h1>`（**重复**）；
  只把报告标题放 **markdown 第一行 H1** ⇒ 飞书把它提为**文档标题**，正文紧随其后
- 最终文档头实测：`<title>内容审查报告 · rv-20261003-082840</title><ul><li>内容 ID：…`
  ⇒ **首块即标题、无前导空块、无重复 H1**
- 写已有文档用 `docs +update --command overwrite`（整篇覆盖）；**禁 `append`** —— append 就是从中间写

**幂等（重复发布不产生垃圾）**：

- 表行：按 `内容 ID` 查 → 命中则 `+record-batch-update`，否则 `+record-batch-create`
- 文档：命中既有行的 `报告链接` ⇒ **复用那篇覆盖**（不新建）；显式 `--doc <token>` 可指定
- 实测：连发两次 ⇒ 同一文档 `HwhWdBp4boWTLXxWPx4cCx75nqg`、同一行 `recvwWu0Ej6uzF`，**无新增**

**第二批新踩的坑（已写进脚本注释与 skill 正文）**：

1. `+record-search` **默认输出 markdown 表格**，`json.loads` 会失败 ⇒ 必须显式 `--format json`；
   记录 id 在 `data.record_id_list`（**不是** `data.records`）。
   第一次修之前正是因为这个，「upsert」退化成了「又建一行」（表里出现两行，已清理）。
2. 默认输出 markdown 的还有 `+record-get` / `+record-list` —— 人读友好、**机读不可**。
3. 文档维度不幂等会**越跑越多**：先建文档、后查行 = 每次新建一篇；
   正确顺序是**先查行，再决定建/覆盖**。

**本轮最终飞书状态（探测件）**：表行 `recvwWu0Ej6uzF` ｜ 文档
`https://momcozy-in.feishu.cn/docx/HwhWdBp4boWTLXxWPx4cCx75nqg`（可删，命令见 §六）。

## 八、行序：新报告必须在**表格第一行**（2026-10-03 晚，用户要求）

**问题**：飞书多维表格按**创建顺序**排列记录，发布件是「追加」，所以新报告落在**末尾/中间** ——
用户打开登记表看到的是「新的在最下面」。bitable **没有**"插到指定位置"的 API（记录本身没有位置属性）。

**做法**（不动列语义、不写假数据）：

1. 表内新增字段 `写入时间`，类型 = **`created_at` 自动字段** —— 建记录时自动填，
   并**已回填历史行**（实测：昨天 22:48 那批行也有值）⇒ **发布件不需要写这个字段**。
2. 给登记视图 `vewhS7Rwx0` 设排序：`写入时间` **倒序**。

```bash
lark-cli --profile dsh-kb base +field-create --base-token <base> --table-id <tbl> \
  --json '[{"field_name":"写入时间","type":"created_at"}]' --as bot
lark-cli --profile dsh-kb base +view-set-sort --base-token <base> --table-id <tbl> \
  --view-id vewhS7Rwx0 --json '{"sort_config":[{"field":"写入时间","desc":true}]}' --as bot
```

**实测**（设完之后按视图排序取数）：

```
1. AUTO-d3f0a215e427   REVIEW   写入时间=10-03 08:55   ← 刚发布的那条，已在第一行
2. （另一会话留的空行）          写入时间=10-03 08:49
3. text-9daefb3b18df   BLOCK    写入时间=10-02 22:48
4. text-ff8f39044dd8   REVIEW   写入时间=10-02 22:48
```

**两个坑 / 两点说明**：

- **没有**去动 `发布时间`：它的语义是「内容发布时间」，拿它当写入时间会污染数据（PRD 也不允许）。
  宁可新增一个自动字段。
- 这是**共享视图配置**变更（所有人看到的顺序都变）——撤销：
  `+view-set-sort --json '{"sort_config":[]}'`；连同字段一起撤：`+field-delete` 删 `写入时间`。
- PRD 口径：表由 15 字段变 **16 字段**（多的那个是自动字段，原 15 列一字未动），已登记在
  `report-output-contract.yaml → applied_20261003.bitable_row_order`。
- `+record-list --view-id` **不套用视图排序**（只按创建顺序返回）；要验顺序得用
  `--sort-json '[{"field":"写入时间","desc":true}]'`，或直接看飞书界面。

## 九、依据来自第几层？（2026-10-03，用户提问 + 落地 L0 直链）

用户问：「报告中的依据来自第几层？」并指出「要取 L0 层的源数据（飞书侧对齐的数据）才方便定位」。

**逐层追一遍**（以用户引用的 `#品线内容边界规则库/recvuJP1LV8KLr/检测关键词` / sha `49c1781f…` 为例）：

| 层 | 这条依据里对应什么 | 落点 |
|---|---|---|
| **L4** | 条款号 **W-1.6**（rule_code `H07`、`status=stable`、`p_level=P1`） | `kb/l4/canonical/wording_entry.jsonl` |
| **L3** | 规则文本（疼痛功效承诺…）＋命中词表 | 由 L2 单元蒸馏 |
| **L2** | 单元 `59aaa138abb8211fca96`（anchor `…/检测关键词`；该记录下共 **12 个单元**） | `kb/l2/units.jsonl` |
| **L1** | 按字段拆的抽取段落（`field_value`） | `kb/l1/3_措辞表达库/bitable__…__recvuJP1LV8KLr.json` |
| **L0** | 记录 sha256 `49c1781fadff4539d4b79ac217916465065ff76085807af92b12786c36237eca`、`entry_url`、`path`、`observed_at=20260923-1117` | `kb/l0/3_措辞表达库/feishu_bitable_record__…__recvuJP1LV8KLr.json` |

**结论**：`库` = 子库标签；**`anchor` ＋ `source_sha256` = L0 的坐标与指纹**（L1 抽取时生成、逐层带到 L4）；
规则文本 / 命中片段 = **L3**；条款号 = **L4**；逐字原文 = **L0 字段值**。
引擎实际是在 **L3 ＋ L5 ＋ L6** 上检索命中，再把 L0 溯源字段一并带出来。

**据此对发布件做的改动**：每条依据新增三行 ——

```
- L0 定位（源数据·飞书）：https://momcozy-in.feishu.cn/base/Lk3Qb8y2QaVyZns6gprcVNE9nA0?table=tblD1MiUK1v5fdjD&record=<rec>
  - 表 <表名> ／ 记录 <rec> ／ 字段 <字段名> ／ 对齐时间 <observed_at> ／ 库内路径 kb/l0/…
  - L0 sha256 <前24位>…：与报告引用值**逐字一致** ✅（比对，不是重算）＋ L2 单元 <unit_id>
```

**一条必须写清的边界**：L0 的 sha **无法本地重算** —— `sha256_input = "record_fields"`
（被哈希的字段 blob 不在本地 L0 件里，只记了这个字面量），所以报告只能声明「**与 L0 记录值比对一致**」；
要真核对**必须点飞书直链**。这一条已写进 `~/.dsh/AGENTS.md` 的溯源四段下方（sha 措辞红线）。

**实测**：docx `AJ8ZdB3M3oU5jNxeuaucrIPBnLf` 里已带上述三行（W-1.16 ／ `recvuJP2jyeza5` 那条）。
