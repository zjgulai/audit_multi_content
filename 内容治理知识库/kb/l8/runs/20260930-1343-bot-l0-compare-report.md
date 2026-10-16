# L0 ↔ 飞书侧 对账报告（RUN 20260930-1343-bot）

> 生成时间（墙钟）：2026-09-30 13:50 +0800
> 问题：「L0 和飞书侧对不齐，有条记录在库里找不到，只对账 L0，别往下游跑。」
> 档位：**`--check`（只读档）** —— 阶段 0、1、2 + 10 + 收尾。**未跑阶段 3–8（写操作，需人确认）、未跑阶段 9/9.5（下游）**。
> 身份：bot（守衡 / dsh-kb）；飞书侧全程只读，零改动。

## 一、一句话结论

**记录层没有漏抓：8 张可读表 557 条逐条逐字段一致，`only_l0`=0、`changed`=0。**
你「找不到的那条记录」几乎可以确定是 `材料收集` 里 **10 条 `材料审核状态` 为空的记录** ——
它们不是丢了，是按**用户指令③**（只抓「审核状态 == 通过」）**有意不入 L0**，
文件已归档在 `kb/l0/_archive/材料收集-未通过-20260929-1045/`（本轮实测 **10/10 都在**）。

**但有一个真盲区**：2 张表本轮**读不到**（395 + 7 条记录），如果那条记录在这两张表里，本轮**无法核**。

---

## 二、记录层四类计数（阶段 1）

| 表 | 飞书 | L0 | 一致 | 飞书多 | L0多 | 值变 |
|---|---|---|---|---|---|---|
| 负面样本 | 115 | 115 | 115 | 0 | 0 | 0 |
| 材料收集 | 32 | 22 | 22 | **10** | 0 | 0 |
| 知识库分类说明 | 5 | 5 | 5 | 0 | 0 | 0 |
| 广告文案明细 | 291 | 291 | 291 | 0 | 0 | 0 |
| 品线内容边界规则库 | 21 | 21 | 21 | 0 | 0 | 0 |
| W1卖点表达边界（品线反馈0910） | 19 | 19 | 19 | 0 | 0 | 0 |
| 风险文案改写建议库（分型号分渠道） | 52 | 52 | 52 | 0 | 0 | 0 |
| 数据表 | 32 | 32 | 32 | 0 | 0 | 0 |
| 专家修订汇总表 | — | 395 | — | — | — | — |
| 内容公式（仅供参考） | — | 7 | — | — | — | — |
| **合计** | | | **557** | **10** | **0** | **0** |

- `manifest` 未登记的 L0 记录文件：**0**（磁盘有记录文件、台账无行 = 0，下游不会被漏抽）
- 拉取失败 **2** 张表（见 §六）
- 全库 959 个 L0 记录文件：**0 个**空/残缺（我另做了独立检查）

## 三、那 10 条「飞书有、L0 无」是什么（这就是本次问题的答案）

10 条的 `材料审核状态` **全部为空**；22 条入库的**全部为「通过」**。两边分类**零交叉**：

```
在 L0 的 22 条状态分布: {'通过': 22}
不在 L0 的 10 条状态分布: {'EMPTY[]': 10}
```

| 编号 | record_id | 材料标题 | 知识库分类 |
|---|---|---|---|
| 1 | `recvvg2wL2EnC0` | MOMCOZY吸奶器产品信息内容汇总 | 产品描述库 |
| 2 | `recvvg2wL2qE3K` | MOMCOZY婴幼儿品线产品信息内容汇总 | 产品描述库 |
| 4 | `recvvg2wL26SAU` | W1卖点匹配证据库_检索阅读版_0827更新 | 产品描述库 |
| 7 | `recvvhv1cwO2Ry` | 202608 营销内容生命周期内容合规审核规范建设-需求框架整理 | 其它 |
| 8 | `recvvhI3yZULdA` | 【创意】需求排期与任务管理 | 素材库 |
| 9 | `recvvlspM5RDoj` | 广告创意跟进 | 素材库 |
| 10 | `recvvltvfBsoDP` | 品线SEO任务管理系统 | 素材库 |
| 11 | `recvvlGAKpUVF9` | 英语站站点blog全表 | 素材库 |
| 14 | `recvvlGUajvYY0` | Momcozy DeepClean Bottle Washer (D8) Materials | 素材库 |
| 16 | `recvvlO5gFdyzx` | MOMCOZY喂养品线产品信息内容汇总 | 产品描述库 |

### 三证齐（不是丢失，是有意不入库）

1. **口径在代码里**：`kb/l8/ingest_l0_new_records.py` 的 `ADMISSION`
   = `{"材料收集": {"mode": "gate", "field": "材料审核状态", "equals": ["通过"], "rule": "用户指令③"}}`
2. **台账有行有原因**：10 条在 `manifest.jsonl` 里 `status=gone`，
   `status_reason` = 「材料收集审核状态非「通过」：按用户指令③（只抓审核通过）不入 L0；文件已归档 …；**仍在飞书表中**」
3. **归档里 10/10 都在**（本轮实测）：
   `kb/l0/_archive/材料收集-未通过-20260929-1045/` —— `recvvg2wL26SAU` … `recvvltvfBsoDP` 逐条命中

> 编号 1/2/4/7/8/9/10/11/14/16 正好是编号序列里断续的那些，与飞书侧 32 条逐一对应；
> 编号 3、28 两边都没有（飞书自动编号的空档），不是丢失。

## 四、结构层（阶段 2）

8 张可读表逐表比对 `field_id ↔ 字段名 ↔ 类型`：**改名 0 / L0 缺字段 0 / 飞书已删 0 / 类型漂移 0**。

| 表 | 字段数 |
|---|---|
| 负面样本 | 16 |
| 材料收集 | 9 |
| 知识库分类说明 | 5 |
| 广告文案明细 | 27 |
| 品线内容边界规则库 | 12 |
| W1卖点表达边界（品线反馈0910） | 8 |
| 风险文案改写建议库（分型号分渠道） | 16 |
| 数据表 | 17 |

取字段失败 **2** 张（专家修订汇总表、内容公式（仅供参考），见 §六）。
**未加 `--apply`，registry 快照未刷新**；脚本在字段读失败时**拒写快照**（未产生 0 字段退化快照）。

## 五、覆盖率矩阵（`S_feishu ⊆ S_report`）

`S_feishu` 取自 `kb/l0/manifest.jsonl` 的 `source_kind` 分布。
⚠️ 非记录类（阶段 5–8）本轮**未重跑**（属 `--sync` 写操作档，需人放行）；
状态引自同一会话窗口内最近的运行产物，**已标注来源与新鲜度**。

| 资源类型 | 状态 | 条数 | 原因码 / 本轮结论 | 证据 |
|---|---|---|---|---|
| `feishu_bitable_record` 表格记录 | **已对齐**（本轮亲测） | 2833 行 / 557 一致 | 10 条属预期不入库；2 表读不到 | `20260930-1343-bot-l0-align.json` |
| `feishu_bitable_table` 字段结构 | **已对齐**（本轮亲测） | 27 / 8 表已比 | 2 表 `91403` + `token_missing` | `20260930-1343-bot-l0-schema-align.json` |
| `feishu_bitable_base` | 部分读不到 | 16 | 4 可达；`wiki:` 形态需 user | `20260930-1343-bot-l0-nonrecord-verify.json` |
| `feishu_attachment` 图片/附件 | 已对齐 | 1722 | 字节 304/304 一致、0 变更、0 下载失败 | `20260930-1258-attachment-bytes-compare.json` |
| 视频素材 | **不适用（附证据）** | 0 | 字段级非空筛选 **0/115** | `20260930-1258-video-filter.json` |
| `feishu_file` 云空间文件 | 读不到 | 42 | `unreachable` 3（token lookup 失败 `981004`）+ 其余已登记 | 同上 nonrecord-verify |
| `feishu_doc` docx | 读不到 | 28 | `unreachable` 1（`docx:Kts8dacyIo1zq1xElWOcqW1zncc`） | 同上 |
| `feishu_sheet` 电子表格 | 部分漂移 | 8 | `drift` 1（`sheets:BX0QshqWThhY6HtDEFCcnMpsnRc`） | 同上 |
| `feishu_slides` 幻灯片 | 已对齐 | 9 | `slides +xml-get` 通道可用 | 同上 |
| `url` 内嵌/外链 | 不可核（口径混） | 674 | 核验 150：`same` 11 / `recomputed_differ` 122 / `unreachable` 17；**混口径，不能算严格一致** | `20260930-1125-l0-url-verify.json` |
| 其它 / 未知 | 已登记 | 3（`source_kind=null`） | 逐条有状态，无空值 | `manifest.jsonl` |

**非记录核验汇总**（184 条）：`ok` 19 ｜ `unreachable` 9 ｜ `drift` 2 ｜ `forbidden` 1 ｜ `not_verified` 153（其中 150 条是 URL，本脚本无 URL 核验器，交由 `verify_l0_urls.py`）。

## 六、缺口清单（对象 + 原因码 + 要人做什么 + 复开条件）

### 6.1 真阻断：2 张表本轮完全读不到（★ 这是你那条记录最可能的藏身处）

```text
对象     : Base SKkkbdZi9aRuMzs7ob0cpSYHnQg
           · 专家修订汇总表 tbl8AI00JZO1iZtp   （L0 侧已有 395 条记录文件）
           · 内容公式（仅供参考） tblVdl0jdK9G4ld3（L0 侧已有 7 条记录文件）
原因码   : bot → 91403 you don't have permission
           user → token_missing（登录态未就绪）
要人做   : ① 把「守衡」(cli_aa2243de0438dcd7) 加成该 Base 的**可阅读协作者**（推荐，一次性）；
           或 ② 重新登录 user 身份（设备码，一次只发一条）
复开条件 : 加入协作者后 bot 直接可读；或 user 重新登录后 L8_AS=user 重跑阶段 1/2
重试策略 : 条件变化后由下一轮同步自动覆盖，本轮不重试
```

**影响**：这 402 条记录（395 + 7）本轮**一条都没能核对**。你找不到的那条如果属于「专家修订」或「内容公式」，本轮**给不出结论** —— 这是 `读不到`，不是 `已对齐`。

### 6.2 非记录层缺口

```text
对象     : wiki 节点 9 条（unreachable）+ 1 条 forbidden（wiki:EsCdw2A7tiz67Rk8LgMce2TAnEh）
原因码   : no_permission / 资源级 ACL（wiki 需 user 身份，而 user 登录态未就绪）
要人做   : 重新登录 user 身份
复开条件 : user 登录恢复后重跑阶段 5
重试策略 : 不重试
```

```text
对象     : docx:Kts8dacyIo1zq1xElWOcqW1zncc、file:HUngb4wwpovNsXxapcIcH2RZnyb 等 3 个 file
原因码   : unreachable（981004 token lookup failed）
要人做   : 确认这些 token 是否已随文档移动/删除
复开条件 : token 重新可达后重跑阶段 5
```

### 6.3 每轮必修的 scope 欠账

`close_stale_scope_gaps.py` 上一轮（1340-bot）干跑：**待关 0** —— 现存 9 条（8 file + 1 sheet）不属于「脚本能补读」那类。

## 七、口径层（结论第 ④ 段）

**URL 层不统一，因此本报告不对 URL 层声称「严格一致」。** 实测 `sha256_input` 混用 4 种以上口径：

| 口径 | 行数 |
|---|---|
| `url_text` | 294 |
| `url_text_rendered_v1` | 111 |
| `url_text_refresh_v1` | 136 |
| `feishu_content_v1` / `pdf_ocr_v1` / `pdf_text_untruncated_v1` / `file_bytes` | 121 |

记录层与结构层不受影响（各自口径单一：`record_fields` / `field_id+name+type`）。
这解释了 URL 核验里 122 条 `recomputed_differ` —— **多为口径差异，不是内容真变了**；要下"变了"的结论必须先统一口径重抓。

## 八、重复项审计（A/B/C/D 四段，只读）

| 段 | 数字 | 处置 |
|---|---|---|
| **A 磁盘字节** | 337 文件 / 202 唯一内容 / 72 组重复 / 多占 **468 MB（31.0%）** | **存储策略，要人拍板**，脚本不自动合并 |
| **B 台账行** | 5362 行 / 2112 唯一资源 / 空转再登记 **1621** 行 | 工具问题：新写入须走 `l0_ledger.append_changed()` |
| **C 记录层** | 959 文件 / 重复 `record_id` **0** / 内容相同记录 **0** 组 | **干净** |
| **D 差集** | 磁盘有台账无 1 / 台账有磁盘无 1127 / **声称有字节却没文件 1** | 见下 |

- D 段 `bytes_claimed_but_missing`：`url:https://hapa8fkuicz.feishu.cn/wiki/XVgVw8WZ3iZsTkkqEpwcbwjJnPh`（`status=updated` 但磁盘无文件）
- D 段 `on_disk_not_in_ledger`：`FNAwb8MLEoWxFmxOuLycGwlfn5g`
- 「台账有磁盘无 1127」中，属于 `feishu_bitable_record` 的 336 条**全部 `status=gone`**（已被整批替换后归档，见 §九），不是缺陷

> **A 段的 72 组重复不要当 bug 去删**：同一张图挂在 21 个不同 `file_token` 下是**飞书侧事实**，删掉等于篡改源状态。

## 九、为什么 L0 是干净的：两批归档已收口

| 归档 | 条数 | 原因 |
|---|---|---|
| `_archive/材料收集-未通过-20260929-1045/` | 10（+2 说明） | 用户指令③：审核状态非「通过」 |
| `_archive/正面和负面样本-superseded-20260929-1045/` | 326 | 飞书侧整批替换（原 `record_id` 返 `Record not found`） |

两批在台账里都是 `status=gone` 且带 `status_reason`，**移动不删除**，可回溯。

## 十、阶段 10 收口核验

| 检查 | 结果 | 归属 |
|---|---|---|
| `workflow_check` ① 环境与版本纪律 | PASS | — |
| ② 权威库 l0~l6 未被改动 | FAIL | **与 L0 无关**，见下 |
| ③ 前序产物哈希（45 项） | FAIL | **与 L0 无关**，见下 |
| ④ 分层库→生成器→视图 | PASS | — |
| ⑤ 装载位→加载器 | PASS | — |
| ⑥ 文档可见性 | FAIL | 510 个「他人产物 hostlib」不可读 |
| ⑦⑧⑨ 消费侧 / 工作台 / 写入侧 | PASS | — |
| `roundtrip_check` | **崩溃** | `kb/view/3_措辞表达库/L2-concepts/cg-r-006445396c95aa10.md` 不存在 |
| `projection_reconcile` | ok=false（3/6 通过，3 项漂移） | 投影层 `owner` 等 4 字段 |
| `envelope_census` | FAIL（活路径 1 个） | `l7/skills/kb-media-extractor-fix/SKILL.md` |

### ② 与 ③ 的 FAIL **不是 L0 的问题**（分级结论）

`workflow_check` ② 的 detail 明确写着：

```json
"l0": {"tree_sha256_16": "5f2256e5443a7c56", "match_L5_baseline": true, "files": 3608},
"l1": {"match_L5_baseline": true},
"l2": {"match_L5_baseline": true},
"l3_whole1527_matches_L4": false        ← 红在这里
```

**l0 / l1 / l2 全部匹配基线；红的是 L3。** ③ 的 17 项 mismatch 也全在
`kb/l3/candidates/rules.jsonl`、`kb/l4/`、`kb/l6/`、`kb/l7/` —— **没有一项是 L0**。

**因何而变**：本机**同时有另一个会话在跑**（`kb/l7/scripts/*_gate.py`、`kb/.work/publish.log` 13:37、
`kb/l3/_archive/rejected-pre-20260930-1341.jsonl`、`kb/l7/reports/20260930-134500-裁决.md`）。
本 skill 全程只读、未跑下游，**不是本轮同步造成的**。

## 十一、工具/脚本侧问题（与「库的问题」严格分开）

1. **`align_l0_schema.py` 默认身份是 `user`**，而 user 登录态当前未就绪 →
   不加 `L8_AS=bot` 跑会得到「取字段失败 10 / 四类全 0」的假结果。
   本轮首次运行即踩到，改 `L8_AS=bot` 后 8 张表全部正常。
   **建议**：与 `align_l0_feishu.py` 对齐——字段读全失败时不写报告，或报告里加 `invalid: true`，
   否则单看 `summary` 会被误读成「全库零差异」。
2. **`verify_l0_nonrecord.py` 同样默认 `user`**：不加 `L8_AS=bot` 跑出
   `{unreachable: 28, ok: 0}`；换 bot 后复现基线 `{ok: 19, unreachable: 9, drift: 2, not_verified: 153, forbidden: 1}`。
   **同一坑一轮内踩到两次**——建议把这两个脚本的默认身份改成 bot，或让 preflight 的能力矩阵
   直接打印「本阶段该用哪个身份」。
3. **`roundtrip_check.py` 硬崩**：投影里 `L2-concepts/` 目录**是 0 个文件**，
   实体文件实际落在 `L1-facts/` —— 投影层的分层归属与加载器读到的 `rel` 不一致。
   （`kb/.work/hostlib/*/3_措辞表达库/L2-concepts/cg-r-006445396c95aa10.md` 有旧版本。）
   这与 `workflow_check` ④ 里的 `node 落盘失败（-9）→ 退回 python 写盘` 很可能是同一根因。
4. `20260930-1347-feishu-url-recrawl.json`（`targets 40 / ok 0 / stored []`）**不是本轮产物**，来自并行会话。

## 十二、待确认清单（每条四要素；建议项排第一）

### ① 【建议】把「守衡」加进第 2 个 Base 的协作者

- **事实**：`专家修订汇总表` + `内容公式（仅供参考）`，bot `91403`、user `token_missing`，本轮 402 条记录一条未核（`20260930-1343-bot-l0-align.json` 的 `pull_failed: 2`）。
- **我的建议**：**把「守衡」加成该 Base 的可阅读协作者**，一次解决、以后每轮自动可核。
- **理由**：比每轮发设备码便宜；且这是**唯一**能让这两张表进入自动对账的办法；纯读权限，风险低、可逆。
- **取舍**：走 ②「重新登录 user」也行，但 user 登录态会再过期，下次又断；不做的话，这两张表**永远处于盲区**——你那条记录如果在这里，永远查不出来。

### ② 【建议】先确认你丢的是不是那 10 条里的某一条

- **事实**：8 张可读表 `only_l0`=0 / `changed`=0，唯一「飞书有、L0 无」的就是那 10 条（审核状态空），10/10 已归档且仍在飞书表中。
- **我的建议**：**报一下那条记录的标题或编号**（§三 表里有 10 条清单）。若是其中一条，结论就是「按用户指令③ 有意不入库」，不是缺陷。
- **理由**：这能在 1 分钟内把「漏抓」和「按规则排除」分开，避免我去动 L0。
- **取舍**：不确认的话，我只能给「记录层已对齐、10 条属预期」这个结论——对，但没法替你指认具体是哪条。

### ③ 【建议】若确实要让那 10 条入库，改口径而不是改数据

- **事实**：口径由 `ADMISSION["材料收集"]` 的 `equals: ["通过"]` 单一控制点决定（`ingest_l0_new_records.py:86`）。
- **我的建议**：**在飞书侧把要收的记录审核状态置为「通过」**，然后重跑入库；**不要**放宽 `equals` 门槛。
- **理由**：门槛是用户指令③ 的显式要求；改门槛等于让未审核材料进知识库，会污染下游 L1–L3；而改飞书状态是正常业务动作。
- **取舍**：放宽门槛能一次性收全 10 条，但会引入未审核内容；什么都不做则这 10 条持续不在库里（当前状态）。

### ④ 阶段 3–8 要不要跑？（这条我**没有建议**）

- **缺什么信息**：你要的是「只核 L0 现状」还是「把 L0 补到与飞书一致」。前者已做完；后者要跑阶段 5–8（含写操作：附件字节落盘、OCR、链接重抓），按本 skill 档位需**人工放行**。
- **取舍**：不跑 → 非记录层停在「部分读不到 / 混口径」；跑 → 会产生写操作与归档，且当前 wiki 类因 user 未登录仍会失败。
- 回一句「**按你的建议做**」即可放行 ①②③；④ 需要你单独说一句跑或不跑。

## 十三、收尾：L0 本次有没有被改过（弱证据）

```bash
$ wc -l kb/l0/manifest.jsonl
    5362 kb/l0/manifest.jsonl
$ shasum -a 256 kb/l0/manifest.jsonl
37e88cbdfc3c091e8c46153d4b28cdf09f0b8bb46d66d9d14dc0ac3adf94f02e
$ stat -f '%Sm' kb/l0/manifest.jsonl
2026-09-30 13:24:10        # 早于本轮开始 13:41
$ find kb/l0 -newermt '2026-09-30 13:41:00' -type f | wc -l
       0
```

**没有版本控制，以上是弱证据**：只能说明本轮同步没有写 L0，不能说明历史上没被改过。

### 本轮写点（全部在 `kb/l8`，未触碰 l0–l7 权威层）

- `kb/l8/runs/20260930-1343-bot-l0-align.json`
- `kb/l8/runs/20260930-1343-bot-l0-schema-align.json`
- `kb/l8/runs/20260930-1343-bot-l0-nonrecord-verify.json`
- `kb/l8/runs/20260930-1343-bot-l0-dup-audit.json`
- `kb/l8/workflow_check_20260930-1343-bot.json`
- `kb/l8/_stage/feishu-align/20260930-1343-bot/`（快照）
- `kb/l8/retro/ledger.ndjson`（append-only 运行台账）
