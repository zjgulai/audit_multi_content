# `kb/l3/candidates/rules.jsonl` 定稿判定（2026-09-30 15:57）

**被判文件**：`kb/l3/candidates/rules.jsonl`
**判定时快照**：1018 行 ｜ 2,778,734 字节 ｜ `sha256 = aa83d1f98bc86857254bfa4f908ebd6d1a869f868cb04970522d154f776b0dac` ｜ mtime `2026-09-30 15:52:08`
**逐条清单**：`定稿判定-rules.jsonl-20260930-1557.jsonl`（509 行，一个 `rule_id` 一行）
**层身份**：L4 定稿与发布层 · 只读查询（判据全取自 L4 台账与 canonical 四个形态文件，不自行发明标准；本次未写库）

---

## 一、结论（一句话版）

**这个文件里 509 条规则，一条不落，全部已经进 L4 定稿层、拿到条款号 —— 但 0 条能当「已发布版本」用。**
能当的只有「**已编号的定稿快照**」。

| | 条数 | 说明 |
|---|---|---|
| 已定稿（在 L4 canonical，`status=stable`，有条款号） | **509 / 509** | `W-1.1–W-1.56`（56 条，连续）+ `W-2.1–W-2.453`（453 条，连续）—— 措辞表达库 |
| 可当「**已编号的定稿快照**」用 | **509** | 机器晋升（machine-promoted），判据 C1–C8 全过 |
| 可当「**已发布版本**」用 | **0** | `human_spotcheck.done = false`；`kb_version` 仍 `v0`；无 `release_id`；`versions.jsonl` 0 行 |
| 我另外**标出来**的（不宜直接当判断依据） | **56** | 全是被 L3 台账判「未过三重验证、不得进判断层」的 `form=entry` 那批 —— 清单见 §四 |

> 也就是说：**「哪几条已定稿」= 全部 509 条；「哪几条还不能当定稿」在本文件里 = 0 条。**
> 真正还不能当定稿的是**另一个文件**：`kb/l3/candidates/external_standard.jsonl` 的 **123 条**（§五）。

**判定依据不是本文件里的 `article_no` 字段** —— 本文件 1018 行里，头 509 行 `article_no` 全是空串。空串 ≠ 没定稿（这是候选件的字段约定：条款号由 L4 发放、L3 侧留空）。判「定稿了没」永远看 L4。

---

## 二、依据（都可复算，命令见 §七）

### 2.1 定稿层逐条命中，且三处台账全等

- 命中 `kb/l4/canonical/wording_entry.jsonl`(56) + `kb/l4/canonical/wording_revision_pair.jsonl`(453) = **509 条**，
  全部 `status=stable`、`promoted_from=provisional`、`promoted_at_run=20260929-1100`、`effective_from=2026-09-29`。
- 集合对账（按 `rule_id`）：候选有 canonical 无 **0 条**；canonical 有候选无 **0 条**；台账 `assignments`(509) 与候选、canonical **两两全等**。
- **条款号三处一致：0 处不一致**（候选追加行的 `article_no` == `kb/l4/registry/l4.json → assignments` == canonical 的 `article_no`）。
- `owner` / `half_life_days` / `valid_until` 全部非空，**无一条过期**（2027-03-28 466 条 ｜ 2026-12-28 22 条 ｜ 2027-09-29 21 条）。
- 509 条 `superseded_by` / `supersedes` / `superseded_at` **全空** → 无一条被取代，不存在「新旧同名」问题。
- L4 记录自足性（正文 / 条款号 / 锚点 / 证据三件套）：**0 个问题**。

### 2.2 闸门放行

| 闸门 | 结果 |
|---|---|
| `kb/kbpy l7/scripts/l4_gate.py` | ✅ 退出码 0，C1–C6 全过（1242 条定稿 ｜ 条款号唯一 ｜ 正文非空 ｜ 证据三件套齐备 ｜ 证据可回指 L2 ｜ canonical/rules.jsonl 保持 0 字节） |
| `kb/kbpy l7/scripts/l3_gate.py` | ✅ 退出码 0（证据全可回指 + 自报键全已声明） |
| `kb/kbpy l7/scripts/l7_gate.py` | ✅ 退出码 0，前置条件全成立（定稿 1242 条，**六要素齐备率 100.0%**）—— 耗时约 8 分钟才出结果 |
| `kb/kbpy l7/scripts/daily_health.py` | ⏱ 跑 ≥3 分钟无输出、被 60 秒超时打断，**健康分本次未取到**，不作为判据（不拿「闸门过」当「已验收」） |

### 2.3 「不能当已发布版本」的依据（原文）

`kb/l4/registry/l4.json`（当前）`promotion_rule`：

> `status` = **待抽查（本批不做）** ｜ `path` = 候选 → 抽查（人工）→ 定稿写 canonical → 才允许冻结版本
> `gate` = **抽查未过不得晋升**

`kb/l4/_pre-rebuild-20260930-1550/l4.registry.json.bak`（15:50 重建前的台账，保留着更完整的口径）：

> `status_enum` = [待抽查（未晋升）, **机器晋升（machine-promoted）· 人工抽查未做**, 抽查通过（human-verified）]
> `human_spotcheck` = `{done: false, who: null, at: null}`，`consequence` = kb_version 保持 v0、不追版本行、不产生 release_id
> `what_it_means` = 只允许当「已编号的定稿快照」用；**不允许当「已发布版本」用**

---

## 三、这个文件本身不好判的两件事（实测）

### 3.1 1018 行 = 509 个 `rule_id` × 2 行（同一 id 出现两行）

| 行区间 | 行数 | `article_no` | 来历 |
|---|---|---|---|
| 1–509 | 509 | **全空** | L3 蒸馏产出（`kb/l8/l3_distill_run.py`） |
| 510–1018 | 509 | `W-1.x` / `W-2.x` | `kb/.work/l4_article.py` 写 canonical 时对候选追加的带号行 |

**实测**：两块的 `rule_id` 集合完全相同；除 `article_no` 外**逐字一致，0 处漂移**（含 `rule_text`/`anchor`/`evidence_units`）。
按「行数」统计会得出 1018 条（×2 的假数），按「唯一 `rule_id`」才是 509 条。

### 3.2 这个文件缺 L4 的治理字段，且有 49 条字段过期 —— **别拿它当治理读数**

| 字段 | 本文件（509 行） | L4 canonical（同 509 条） |
|---|---|---|
| `owner` | 全部空值 | 474「法务」｜14「法务 + 产品负责人」｜13「法务 + 渠道负责人」｜8「法务 + 医学顾问」 |
| `effective_from` | 全部空值 | 全部 `2026-09-29`（策略基线日；源侧无条文生效日，见 `kb/l3/registry/half-life-policy.json` 的 honest_limits） |
| `half_life_days` | **字段不存在** | 180 / 90 / 365（分型政策） |
| `valid_until` | **字段不存在** | 2027-03-28 / 2026-12-28 / 2027-09-29 |
| 有 `rule_code` | 16 条 | **37 条** |
| `verification` | `已归纳` 124 ｜ `待验证` 894（**两套口径**，见下） | `已支持` 62 ｜ `待验证` 447 |
| `p_level` | 未拆分的粗判（P2 32 / P1 986 行） | 已细分 P0 21 ｜ P1 477 ｜ P2 7 ｜ P3 4 |

**49 条字段漂移，且全部落在同一个子集里**（= `form=entry` 那 56 条，见 §四）：

| 漂移组合 | 条数 |
|---|---|
| `p_level` + `suggested_replacement` | 12 |
| `p_level` | 16 |
| `p_level` + `rule_code` | 14 |
| `rule_code` | 7 |
| **合计** | **49**（56 条中 49 条不一致，7 条一致） |

漂移方向（候选 → L4）：`p_level` P2→P0 6 处、P2→P1 10 处、P1→P0 15 处、P1→P3 4 处、P1→P2 7 处；`rule_code` 21 处全是「候选空 → L4 有值（H01–H09 / M01–M07 / U01–U04）」。

**这两套值按台账先后应当以 L4 为准**：L3 台账 `appended_fields.p_level_refined` 自己写明「**上一批把入口规则统一记为 P2、仅当任一记录高危才 P0，判据过粗；本批按源侧风险信号精确化**」——
本文件里留的正是那句被判「过粗」的旧值。**我按技能红线只报冲突、不替人选值**（完整对照表见 `定稿判定-rules.jsonl-20260930-1557.jsonl` 的 `drift_fields`，以及本目录 `定稿判定-漂移对照表-20260930-1557.md`）。

> `verification` 两套口径说明：L3 台账 `verification_policy` 的规则是 `support_count==1 → 待验证；>=2 → 已支持`（L4 严格照此，62/447）。
> 本文件里的 `已归纳/待验证` 是另一套（`已归纳` 124 条），按 `support_count` 折算后 **62 条在 L4 是「已支持」**，即本文件该字段也落后于 L4。

---

## 四、我另外标出来的 56 条：已编号，但**不宜直接当判断依据**

这 56 条 **已定稿、有号**（结论不变），但 L3 台账 `kb/l3/registry/l3.json → e021_concepts` 对它们逐条写明：

> 「三重验证是人工判断闸门；派生视图无权替人打分，编一个等于把闸门变成自我申报。故明确标注「**未验证、不得进判断层**」并从本批产出中排除」
> `verdicts` = `{已排除: 56, 已补三重验证: 0}`

**这 56 条 = 本文件里 `form=entry` 的全部（W-1.1 … W-1.56），集合完全重合（差值 0）。**
它们同时是 `P0` 的主要来源（21 条 P0 全在这一段），且 **49 条字段漂移全部落在这一段** —— 即本文件里这段的副本既没验证过、又是旧值。

标题清单（完整理由见逐条 JSONL 的 `flags`）：

**全部 56 条（W-1.1 … W-1.56，一条不落）**：

| 条款号 | rule_id | 标记 |
|---|---|---|
| W-1.1 | `r-006445396c95aa10` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.2 | `r-039822ed5c8e3448` | 未过三重验证 ｜ authority=inferred |
| W-1.3 | `r-03fb6f7a5fe1655a` | 未过三重验证 ｜ authority=inferred |
| W-1.4 | `r-0823b2d08a7e4ec2` | 未过三重验证 ｜ authority=inferred |
| W-1.5 | `r-0ffc53715dfa4e43` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.6 | `r-106e4c5b6475d0e3` | 未过三重验证 ｜ authority=inferred |
| W-1.7 | `r-13fd137cd293d657` | 未过三重验证 ｜ authority=inferred ｜ risk_level=unknown |
| W-1.8 | `r-15a607c4457c8b55` | 未过三重验证 ｜ authority=inferred |
| W-1.9 | `r-16cac1c85580f8f7` | 未过三重验证 ｜ authority=inferred |
| W-1.10 | `r-1cf94543649842a0` | 未过三重验证 ｜ authority=inferred |
| W-1.11 | `r-21786ac5aff9be34` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.12 | `r-252ba6cf5ee92b00` | 未过三重验证 ｜ authority=inferred |
| W-1.13 | `r-3055901e5877f981` | 未过三重验证 ｜ **本文件副本漂移：p_level** |
| W-1.14 | `r-30d3b9b54135fa04` | 未过三重验证 ｜ authority=inferred |
| W-1.15 | `r-335f00d14cefe7f9` | 未过三重验证 ｜ authority=inferred |
| W-1.16 | `r-33ce99a813e0865a` | 未过三重验证 ｜ authority=inferred |
| W-1.17 | `r-379572868aa01151` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.18 | `r-37b49eadb72d7dc2` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.19 | `r-38148746d4e6516d` | 未过三重验证 ｜ authority=inferred |
| W-1.20 | `r-3b18c7d1af8f8d4d` | 未过三重验证 ｜ **本文件副本漂移：p_level** |
| W-1.21 | `r-3b3460eab4528002` | 未过三重验证 ｜ authority=inferred |
| W-1.22 | `r-3b6c3c82dc667295` | 未过三重验证 ｜ authority=inferred |
| W-1.23 | `r-4142a3c2dbf3cbe5` | 未过三重验证 ｜ authority=inferred |
| W-1.24 | `r-478f43899bcb5b8a` | 未过三重验证 ｜ authority=inferred |
| W-1.25 | `r-4f309d6ebde80283` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.26 | `r-5c056bc02cdd770c` | 未过三重验证 ｜ authority=inferred |
| W-1.27 | `r-65198e7c3e5b833e` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.28 | `r-6773cda1135632c8` | 未过三重验证 ｜ authority=inferred |
| W-1.29 | `r-69f4049b9cd733ea` | 未过三重验证 ｜ authority=inferred |
| W-1.30 | `r-724b26ecb1dee9c4` | 未过三重验证 ｜ authority=inferred |
| W-1.31 | `r-7489e156a5d2c7b2` | 未过三重验证 ｜ authority=inferred |
| W-1.32 | `r-755d3407cf8ce75b` | 未过三重验证 ｜ authority=inferred |
| W-1.33 | `r-7baf7ceb47b2e5bc` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.34 | `r-7bed60d9dd01793a` | 未过三重验证 ｜ authority=inferred |
| W-1.35 | `r-85348bba00a2b5a7` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.36 | `r-870bf797d240b725` | 未过三重验证 ｜ authority=inferred |
| W-1.37 | `r-8dfbcdca24e18a60` | 未过三重验证 ｜ authority=inferred |
| W-1.38 | `r-8e049d8b38a8ac31` | 未过三重验证 ｜ authority=inferred |
| W-1.39 | `r-97044c3283e41aea` | 未过三重验证 ｜ authority=inferred |
| W-1.40 | `r-9878294c87d29582` | 未过三重验证 ｜ authority=inferred |
| W-1.41 | `r-9b672eff05199974` | 未过三重验证 ｜ authority=inferred |
| W-1.42 | `r-9e252d15425a4179` | 未过三重验证 ｜ authority=inferred |
| W-1.43 | `r-b10ee2b8361c8a3d` | 未过三重验证 ｜ authority=inferred |
| W-1.44 | `r-b301be45b8cd64a9` | 未过三重验证 ｜ authority=inferred |
| W-1.45 | `r-b3d0d5f656f0df34` | 未过三重验证 ｜ authority=inferred |
| W-1.46 | `r-b8669712e27146e3` | 未过三重验证 ｜ authority=inferred |
| W-1.47 | `r-b8aea07e90a86b59` | 未过三重验证 ｜ authority=inferred |
| W-1.48 | `r-c40ed52e71a07743` | 未过三重验证 ｜ authority=inferred |
| W-1.49 | `r-c767bb12e6a8698d` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.50 | `r-cbfa62aa397fc6ba` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.51 | `r-d00103c52a98512e` | 未过三重验证 ｜ authority=inferred |
| W-1.52 | `r-d451847b1d6b75f4` | 未过三重验证 ｜ authority=inferred |
| W-1.53 | `r-d7290a0ee59c58ef` | 未过三重验证 ｜ **本文件副本漂移：p_level/suggested_replacement** |
| W-1.54 | `r-ddf0f8360c7b53a7` | 未过三重验证 ｜ authority=inferred |
| W-1.55 | `r-e879231d61c9bd08` | 未过三重验证 ｜ **本文件副本漂移：p_level** |
| W-1.56 | `r-e919fda20cd2f95e` | 未过三重验证 ｜ authority=inferred |

> 注意 §五 末尾那条：**别把它读成「这 56 条不算定稿」** —— 它是 L3 派生视图的分层口径（派生视图不得替人过闸），不是 L4 定稿口径。进了评审链当判断依据时需另核。

除此之外，**只标注、不阻断**的质量线索（数量已核）：

| 线索 | 条数 | 说明 |
|---|---|---|
| `support_count = 1`（`verification=待验证`） | 447 | 全是 `atomic`（一对修订天然只有一条支撑），按 L3 台账口径**正常**；26 条 `inductive` **全部** `support_count ≥ 2`，无证据不足的归纳型 |
| `authority = inferred`（模型归纳，无外部权威背书） | 93 | 其中 20 条同时是 `inductive` |
| `risk_level = unknown`（未评估风险等级） | 454 | 其余 55 条才有具体风险等级标注 |
| `valid_until = 2026-12-28`（90 天档，最早到期） | 22 | 到期前 30 天应复核（政策见 `half-life-policy.json → revisit`） |

---

## 五、「不能当定稿」的到底在哪

### 5.1 本文件里：0 条

### 5.2 隔壁文件里：`kb/l3/candidates/external_standard.jsonl` —— 123 条候选

| 字段 | 值 |
|---|---|
| `status` / `rule_status` | `candidate` / `provisional` |
| `article_no` | **全部空（未发号）** |
| `verification` | 全部 `待人工复核` |
| `evidence_level` | 全部 `cited` |
| `form` | recommendation 36 / substantiation 24 / disclosure 18 / prohibition 16 / scope 15 / mandate 14 |
| `applicable_jurisdiction` | 全部 `US` ｜ `owner` 全部为空 |

L4 台账 `numbering.totals.libraries_empty = ["external_standard","internal_sample","product_desc","unknown"]` —— 这四类库**一条都没发号**，123 条外部标准候选是其中最大的一批。

### 5.3 术语更正（两处，避免误判）

1. 本文件里的 `status` **全部是 `provisional`（1018/1018）** —— 它写的是「**候选行**的身份」，不是「有没有定稿」。定稿身份在 L4 canonical 的 `status=stable`。只看本文件会误判成「一条都没定稿」。
2. 别查 `kb/l4/canonical/rules.jsonl` —— 恒 **0 字节**（历史迁移留痕，故意保留，L4 闸门 C6 要求它保持 0 字节）。查它必然空，**不等于**「没定稿」。定稿在四个形态文件里。

---

## 六、判完之后需要人看的两件事（只报不改）

1. **台账被换成了精简版**：15:50–15:53 一次 `kb-pipeline --via-skill` 重建后，`kb/l4/registry/l4.json` 的
   `canonical.state`（原「已填（20260929-1100）：四个形态文件，共 1242 条定稿记录；status=stable」）→ 变成「空（本批不写…）」，
   `promotion_rule` 从带 C1–C8 判据 / `human_spotcheck` / 抽样方案的整块缩成 5 行，`repromotions`、`totals_20260924-1320` 两个字段消失。
   **定稿文件本身没被动**：本次实测四个 canonical 文件的 `sha256` 与备份台账声明的**逐字节相同**、行数 1242 不变、闸门仍过。
   但「这 509 条是 `status=stable` 的机器晋升定稿、人工抽查未做」这句话，**现在只存在于备份里**。要不要回写，是人的决定。
2. **49 条字段漂移**（§3.2）：候选副本的 `p_level` / `rule_code` / `suggested_replacement` 与 L4 不一致，且全部集中在被排除的 56 条上。
   L4 闸门的 C5（定稿不改写）只比对 `rule_text` / `anchor`，**不覆盖这三个治理字段，所以闸门不会红** —— 这是闸门的已知盲区，不是闸门失效。
   以哪一侧为准（我倾向 L4，理由见 §3.2 引的 `p_level_refined`），需要人拍一次。

---

## 七、复算方法

```bash
cd ~/.dsh/Momcozy知识库          # = kb/ 的上一级
kb/kbpy l7/scripts/l4_gate.py    # 退出 0 = C1–C6 全过
kb/kbpy l7/scripts/l3_gate.py    # 退出 0 = 证据全可回指

# 逐条判定（本文件同款逻辑；下面这行紧跟 heredoc 起始，不是文档标题）
KB_INTERP_OK=1 /usr/bin/python3 - <<'PY'
import json, glob
cand = [json.loads(l) for l in open('kb/l3/candidates/rules.jsonl', encoding='utf-8') if l.strip()]
head = {r['rule_id']: r for r in cand[:509]}          # 头 509 行：无号
tail = {r['rule_id']: r for r in cand[509:]}          # 尾 509 行：带号
canon = {}
for f in ['kb/l4/canonical/wording_entry.jsonl', 'kb/l4/canonical/wording_revision_pair.jsonl']:
    for r in map(json.loads, open(f, encoding='utf-8')):
        canon[r['rule_id']] = r
print('候选唯一 rule_id:', len(head), '| canonical:', len(canon),
      '| 差集:', len(set(head) ^ set(canon)))
print('条款号不一致:', sum(1 for k in head if tail[k]['article_no'] != canon[k]['article_no']))
print('status 分布:', {s: sum(1 for r in canon.values() if r['status'] == s) for s in {r['status'] for r in canon.values()}})
PY
```

## 八、同目录另有一份 509 行清单，有一列结论更重，但两边的「点」都对（合并时按事实拼）

`定稿判定-L3候选509-20260930-1605.csv`（16:03 落盘，非本报告产出）的 `article_no` 集合与本次 509 条**完全一致**，
「定稿判定=已定稿（已发号）」这一列也一致。分歧只在它的「不能当定稿的原因」列：「**缺 source_sha256（过不了 L7 硬闸门）**」。
把两边的事实对齐（以下都实测过）：

| 事实 | 实测 |
|---|---|
| 行**顶层** `source_sha256` | 509 条**全部为空**（没有这个字段）—— 该列说对了这一半 |
| `cite_check.source_sha256` | 509 条**全部为空值**（键在、值为空）—— 也说对了 |
| `evidence_units[i].source_sha256` | **1729 条证据引用全部有值**（entry 836 ／ revision_pair 893），`evidence_units` 为空的行 **0 条** |
| L4 台账 C2 的明文 | 「规则行的 sha256 位于 `evidence_units[i]` 内（**行上没有该字段**），故不按行核」 |
| L7 闸门取值方式 | `kb/l7/scripts/l7_gate.py:121-134`：样本/条款形态取顶层 `anchor` + `cite_check.source_sha256`；**规则形态取 `evidence_units`** |

所以：**说「顶层与 cite_check 里没有 source_sha256」是事实；直接推成「这 509 条引用不出去」则越过了规则形态的取值路径** ——
规则形态的 sha256 在 `evidence_units` 里、1729 条一条不缺，L7 的契约也认这条路。**真伪已用 L7 闸门跑通定论（16:09 出结果）**：

```
L7 闸门（引用契约的前置条件：库名 / 现行库可复算 / 六要素 / 条款号出处）
  规则候选 1018 条（全部候选 1874 条）｜ 定稿 1242 条 ｜ 六要素齐备 1242 条（覆盖率 100.0%）
结论：✅ 过（前置条件全成立）    退出码：0
```

即：**这 509 条的引用前置条件成立**（六要素齐备率 100%），CSV 那一列「过不了 L7 硬闸门」按现行 L7 实现**不成立**。
（闸门自己声明：运行时引用完整性由评审链 `kb-content-review` 的硬闸门负责，L7 只保证前置条件 —— 所以这里说的是「能引用」，
不是「引用内容一定对」。）另：`daily_health.py` / `l7_gate.py` 都要跑 6–8 分钟才出结果，前几次 60 秒超时是我取数太急，不是脚本坏。

> 另一处口径差异（不影响定稿结论，避免抄错）：`W-2` 段是 **W-2.1 – W-2.453 连续 453 号**，不是 W-2.1–W-2.99。
> 条款号按 `order_key` 发号、只增不改，**号连续 ≠ 规则数**，取用区间时用台账 `numbering.issued` 或本次逐条清单为准。


---

判据出处：`kb/l4/registry/l4.json`（当前）与 `kb/l4/_pre-rebuild-20260930-1550/l4.registry.json.bak`（完整版）、
`kb/l7/scripts/l4_gate.py`、`kb/l3/registry/l3.json`（`verification_policy` / `e021_concepts` / `appended_fields`）、
`kb/l3/registry/half-life-policy.json`。
**本次全程只读**：未写任何库内文件（输出两份报告在本目录，不在 `kb/` 内）。
