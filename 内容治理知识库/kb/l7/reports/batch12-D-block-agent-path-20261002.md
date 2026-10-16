# 批次 12-D：**agent / skill 路径**实测 —— 该 BLOCK 的文案被 skill 链判成 PASS（漏放确认）

- 日期：2026-10-02
- 工作区（= cwd）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 性质：**只测不改**（未修改任何项目文件；本批不实现修复）
- 被测问题：DoD 要求「调用 L0–L7 分层 skill **+ 评审链**」。**API 路径已验证接通；agent/skill 路径未验证。**
- 结论（一句话）：**skill 链自己点名的脚本给出 PASS（置信度 0.99），API 路径给出 BLOCK（10 条依据）—— 两条路结论相反，漏放确认。**

---

## 0. 本报告所有数字的来源

本报告不含估算值。每个数字都来自本批次实际执行的命令输出或实际读取的文件行。
未确定的事项在 §7 单列，不与结论混写。

**须声明的环境事实**：本批次运行期间，同一工作区**存在另一个并发会话**
（`kb/l7/runs/` 里出现多条 `trigger` 以 `FDA approved and hospital grade, the Momcozy S12 P…`
开头的 `review_machine` 记录，内容哈希与本批次的文案不同）。
因此本报告只认领**内容哈希与本批次文案逐字一致**的产物；其余同窗口产物不作归属。

---

## 1. Task 1 —— 被测文案与预期规则

### 1.1 文案（US 市场 / 吸奶器）

```
Momcozy S12 Pro Wearable Breast Pump - FDA approved and hospital grade. 100% safe and pain-free pumping, every time. Mimics baby's natural nursing rhythm to increase milk supply. Doctor recommended by 100+ experts.
```

- 长度：214 字符
- `sha256`（= 本次所有路径的 `content_version`）：
  `de39890f0ce7c05beb4c93130710d98d71d2b2e22e1890c5dc874a93142d16bc`
- 落盘副本：`/tmp/batch12/copy.txt`（+换行）、`/tmp/batch12/copy.json`（`{"text": "..."}`，无换行）

选择理由：它是**知识库自己的规则文件**里已登记的 P0 红线（绝对化 / 虚假安全承诺、监管认证宣称、
疼痛功效承诺、仿生宣称、专家背书、催乳宣称），而不是外部常识判断。逐条见 §1.2。

### 1.2 预期触发的规则（全部取自库内文件原文，逐条给出处）

`kb/l5/p0_patterns.jsonl` 共 7 条 P0 模式，本段文案命中其中 **6 条**，每条 `p_level=P0`、`match_note=BLOCK`：

| 行号（file:line） | rule_code | 命中的库内 pattern（原文） | 对应文案片段 |
|---|---|---|---|
| `kb/l5/p0_patterns.jsonl:1` | H02 | `increase milk supply` / `more milk` | `increase milk supply` |
| `kb/l5/p0_patterns.jsonl:2` | H04 | `doctor recommended` / `recommended by 100+ experts` | `Doctor recommended by 100+ experts` |
| `kb/l5/p0_patterns.jsonl:3` | H05 | `100% safe` | `100% safe` |
| `kb/l5/p0_patterns.jsonl:4` | H06 | `FDA approved` | `FDA approved` |
| `kb/l5/p0_patterns.jsonl:5` | H07 | `pain-free` | `pain-free` |
| `kb/l5/p0_patterns.jsonl:6` | H09 | `mimics baby` | `Mimics baby's natural nursing` |

（`kb/l5/p0_patterns.jsonl:7` = U04 `painful pumping / clogged ducts / sore nipples`，本段**未**命中，如实列出。）

同一预期另有仓库内既有文档背书（非本批次新造的判断）：

- `~/.dsh/skills/文案合规审查/SKILL.md:35-40` 用同一族文案给出实测表：
  「第 1 条（候选扫描）= **0 候选**；第 2 条（509 条规则 + P0 + BM25）= **10 处 BLOCK**」。
- `kb/l7/review-engine/core/with_kb_evidence.py:3-25`（模块 docstring）记同一现象，
  并写明「只跑裁决侧 → `scan_text` 给 0 候选 → `decide()` 倾向 PASS（漏放）；
  只跑依据侧 → 10 处 BLOCK。两条路的输入一模一样、结论相反」。

### 1.3 顺带做的一次基线复算（**与仓库文档不一致，如实记录**）

把 `文案合规审查/SKILL.md:35` 那段**逐字原文**再跑一遍：

```
FDA approved breast pump. Hospital grade. 100% safe and pain-free. Mimics baby natural nursing to boost supply.
```

实测：`state = BLOCK`，`findings = 8`（不是文档写的 10），
条款号 = `W-1.18 / W-1.1 / W-1.31 / W-1.53 / W-1.33 / W-1.8 / W-1.35(REVIEW) / W-1.11(REVIEW)`。
文档列的 `W-1.6 / W-1.19 / W-1.22` 本次**未出现**，`W-1.1` 本次**新出现**。
`kb/l3/candidates/rules.jsonl` 现有 **2036 行**（文档写「509 条」）。
→ **文档里的「10 处 BLOCK / 509 条」是过期口径**；结论方向（BLOCK）不变，条数与条款号已漂移。
（漂移原因本批次**未**判定，不推测。）

---

## 2. Task 1 —— 按 skill 链实际执行（内容审查总控 → 文案合规审查 → 审查裁决）

所有命令均 `export PATH="$HOME/.dsh/bin:$PATH"`，cwd = 工作区根，`kb/kbpy` 代跑。

### 2.1 kb-content-review 的前置条件（该 skill 自己要求先跑）

`~/.dsh/skills/kb-content-review/SKILL.md:96-113` 规定：走检索协议**之前先跑 `freshness.py`**，
退出码 3 = 有层超期 → **拒答，不许出结论**。

命令与输出：

```
$ sh kb/kbpy l7/scripts/freshness.py
...
结论：❌ 有 1 个关键 data 产物超期 → 评审链应**拒答**（退出码 3），不许拿陈旧数据出结论
   · **L4 的 wording_entry.jsonl 落后 2.9 天前**（只看 data 产物）→ 确认它是否该跑（或它的上游还没更新）
REAL EXIT CODE = 3
```

→ **按 kb-content-review 自己的前置条件，整条链此刻应当拒答。**
本批次为了把「两条路是否相反」测出来，在此前提下仍继续执行并逐项记录（下方所有结论都带这条前提）。

### 2.2 内容审查总控（入口）

读取：`~/.dsh/skills/内容审查总控/SKILL.md`

它第 1 步要求按 `kb/l7/review-engine/contracts/review-contract.json` 校验 payload
（该文件 `required` = `review_id / content_id / content_type / content_version / input_manifest / coverage / risk_items`）。
本批次据此构造合法 text-only payload：`/tmp/batch12/payload_decision_only.json`。

它第 23 行**点名文字冒烟入口**：

```bash
$ sh kb/kbpy l7/review-engine/core/review_text.py /tmp/batch12/payload_decision_only.json "$TEXT"
decision = PASS | confidence = 0.99 | issue_count = 0
decision_trace.reasons = ['no_known_blocking_or_review_risk']
summary = 【审查结论：PASS】未发现已知底线风险，可转交 sign-off 负责人确认。
next_owners = ['Sign-off 负责人']
risk_items = 0
EXIT=0
```

**这是 skill 链自己点名的入口脚本，输出 PASS。**

### 2.3 文案合规审查（专项）

读取：`~/.dsh/skills/文案合规审查/SKILL.md`

该 skill §「判据的两条来源（**两条都必须跑**）」：

**第 1 源 —— 候选扫描（`SKILL.md:25`）**

```bash
$ sh kb/kbpy l7/review-engine/core/rule_engine.py "$TEXT"
[]
EXIT=0
```

→ **0 候选。** 与文档 §1.2 记录的实测一致。

**第 2 源 —— 依据主体（`SKILL.md:29-31`，走 kb-content-review 检索协议）**

```bash
$ sh kb/kbpy l7/skills/kb-content-review/scripts/review.py --kb-root "$ROOT" \
      --text "$TEXT" --json --dry-run --findings-out /tmp/batch12/findings.json
EXIT=0
state = BLOCK | run_id = 20261002-073040
findings count = 10
  - r-37b49eadb72d7dc2 | W-1.18 | sev=BLOCK | layer=P0 确定性匹配
  - r-006445396c95aa10 | W-1.1  | sev=BLOCK | layer=P0 确定性匹配（依据不可逐字回源）
  - r-7489e156a5d2c7b2 | W-1.31 | sev=BLOCK | layer=规则层
  - r-d7290a0ee59c58ef | W-1.53 | sev=BLOCK | layer=P0 确定性匹配
  - r-7baf7ceb47b2e5bc | W-1.33 | sev=BLOCK | layer=P0 确定性匹配
  - r-3055901e5877f981 | W-1.13 | sev=BLOCK | layer=P0 确定性匹配
  - r-9b672eff05199974 | W-1.41 | sev=BLOCK | layer=规则层
  - r-15a607c4457c8b55 | W-1.8  | sev=BLOCK | layer=P0 确定性匹配
  - r-85348bba00a2b5a7 | W-1.35 | sev=REVIEW | layer=规则层
  - r-21786ac5aff9be34 | W-1.11 | sev=REVIEW | layer=规则层
```

（`--dry-run` 实测未落盘：stdout 首行 = `[dry-run] 未落盘。目标：…/20261002-073040.review.md｜21148 字节｜164 行`。）

**依据侧结论 = BLOCK，10 处。** 与第 1 源的 0 候选**相反**。

同一份依据侧，用 P0 确定性匹配器单独复核：

```bash
$ sh kb/kbpy l5/matcher.py --text "$TEXT" --json      # EXIT=1（命中）
hit_count(rules) = 6   elapsed_ms = 9.061
  H02 P0 BLOCK  patterns=['increase milk supply', '\b(more|increase[sd]?|boost[s]?|maximi[sz]e[sd]?)\s+(your\s+)?milk\b']
  H04 P0 BLOCK  patterns=['recommended by 100+ experts', 'doctor recommended', '\b(doctor|physician|pediatrician|expert|ibclc|ob[\s-]?gyn)[\s-]*(recommended|approved|endorsed|backed)\b']
  H05 P0 BLOCK  patterns=['100% safe', '\b100\s*%\s*(safe|safety)\b']
  H06 P0 BLOCK  patterns=['FDA approved', '\bFDA\s+(approved|certified)\b', '\bFDA[\s-]*(approved|certified)\b']
  H07 P0 BLOCK  patterns=['pain-free', '\bpain[\s-]*(free|less)\b']
  H09 P0 BLOCK  patterns=['\bmimic(s|king)?\b[^.]{0,30}\bbaby\b']
```

→ 6 条 P0、`match_note=BLOCK`，与 §1.2 的预期**逐条对齐**。

### 2.4 审查裁决（裁决）

读取：`~/.dsh/skills/审查裁决/SKILL.md`

它第 15 行点名 `review_engine.py`：

```bash
$ sh kb/kbpy l7/review-engine/core/review_engine.py /tmp/batch12/payload_decision_only.json
decision = PASS | confidence = 0.99 | issue_count = 0
reasons = ['no_known_blocking_or_review_risk']
summary = 【审查结论：PASS】未发现已知底线风险，可转交 sign-off 负责人确认。
EXIT=0
```

**裁决引擎在链自己给出的输入上，同样输出 PASS。**

### 2.5 对照：交接件（**链没有点名它**）

```bash
$ sh kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "$TEXT"
结论：BLOCK
依据命中 10 处（检索时库内规则 2036 条 + P0 匹配；库规模按运行时实读，不硬编码）
依据来源：本次现跑 review.py
{ "decision": "BLOCK", "confidence": 0.97, "issue_count": 10, ... }
EXIT=0
```

### 2.6 对照组：裁决侧本身没坏

```bash
$ sh kb/kbpy l7/review-engine/core/review_text.py /tmp/batch12/payload_control.json \
    "This pump treats plugged ducts and is the best-selling choice."
decision = REVIEW | issue_count = 2 | reasons = ['uncertain_or_review_item']
```

→ 裁决侧对**它自己那 5 条种子规则**是工作的（REVIEW）。
它对本文案给 PASS，**不是因为引擎坏了，而是因为它的输入里根本没有库内 2036 条规则的依据**。

---

## 3. Task 1 —— 最终三态结论

| # | 谁给的结论 | 结论 |
|---|---|---|
| ① | skill 链**自己点名的脚本**（`内容审查总控:23` → `review_text.py`；`审查裁决:15` → `review_engine.py`） | **PASS**（confidence 0.99，issue_count 0） |
| ② | 专项 skill 的**第 1 源**（`文案合规审查:25` → `rule_engine.py`） | 0 候选（无结论） |
| ③ | 专项 skill 的**第 2 源**（`文案合规审查:29-31` → kb-content-review / `review.py`） | **BLOCK**（10 处） |
| ④ | **交接件**（`with_kb_evidence.py`，**链里没有任何 skill 点名它**） | **BLOCK**（10 处） |
| ⑤ | **API 路径**（`kb_api.py` `POST /review`） | **BLOCK**（10 处） |
| ⑥ | `kb-content-review` 自己的前置条件（`SKILL.md:96-113`） | **应拒答**（freshness 退出码 3） |

### 判定：**漏放成立（miss confirmed）**

- 该文案应当 **BLOCK**（6 条 P0、`match_note=BLOCK`，见 §1.2，全部有 file:line）。
- agent/skill 链**自己点名的脚本**（①）给出的结论是 **PASS**，且置信度 0.99、理由
  `no_known_blocking_or_review_risk` —— 引擎明确断言「**没有已知的阻断或复核风险**」，
  而事实上库内有 10 条依据、其中 8 条 severity=BLOCK。
- 这不是「结论打折」，是**结论反向**：`PASS` ↔ `BLOCK`。

### 补充实测：就算 agent 手动把依据搬进 risk_items，仍可能只到 REVIEW

`review_engine.decide()` 判 BLOCK 的条件（`kb/l7/review-engine/core/review_engine.py:136-138`）是
`action == "block"` **且** `status == "confirmed"` **且** `evidence_complete`。
而 `evidence_complete` 的判据（`:54-55`）是 `bool(location and (evidence_url or evidence_id))`。

实测把 10 条依据**手工**映射成 risk_items（带 `location`，**不带** `evidence_id`/`evidence_url`）：

```
items passed in = 10
decision = REVIEW | issue_count = 10 | reasons = ['uncertain_or_review_item']
evidence_complete values = [False]
```

→ 只有 `with_kb_evidence._to_risk_item()`（`:143-149`）会在**引用契约六要素齐**时写 `evidence_id`，
才把这条推到 BLOCK。**手抄映射得到 REVIEW，正确映射得到 BLOCK。**
所以「把依据接上」这件事**必须由代码做**，人（或 LLM）手抄会掉一档。

---

## 4. Task 2 —— agent 路径实际调用了哪些工具（按执行顺序）

| # | 实际执行的命令 | 属于哪一侧 |
|---|---|---|
| 1 | `sh kb/kbpy l7/scripts/freshness.py` | **别的**（kb-content-review 前置条件；只读供给链新鲜度） |
| 2 | payload 校验：读 `kb/l7/review-engine/contracts/review-contract.json` | **别的**（契约校验，非引擎） |
| 3 | `sh kb/kbpy l7/review-engine/core/review_text.py <payload> "<text>"` | **`review_text.py` 的 `scan_text`（5 条种子规则的裁决侧）** —— `review_text.py:24` |
| 4 | `sh kb/kbpy l7/review-engine/core/rule_engine.py "<text>"` | **`review_text.py` 同源的 `scan_text`（5 条种子规则）**（`rule_engine.py:66`，`review_text.py:24` 调的就是它） |
| 5 | `sh kb/kbpy l7/skills/kb-content-review/scripts/review.py --kb-root … --text … --json --dry-run --findings-out …` | **依据侧**（P0 + 2036 条 + BM25） |
| 6 | `sh kb/kbpy l5/matcher.py --text "<text>" --json` | **依据侧**（P0 确定性匹配） |
| 7 | `sh kb/kbpy l7/review-engine/core/review_engine.py <payload>` | **`review_engine.decide()`**（裁决；**不取依据**） |
| 8 | `sh kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "<text>"` | **依据侧 + 裁决侧**（唯一把两侧接起来的代码） |
| 9 | `KB_INTERP_OK=1 /usr/bin/python3 -m uvicorn kb_api:app --host 127.0.0.1 --port 8799` | **API 路径**（服务，非 skill） |
| 10 | `curl -s -X POST http://127.0.0.1:8799/review …` | **API 路径** |
| 11 | `lsof -nP -iTCP:8799 -sTCP:LISTEN` / `curl 127.0.0.1:8799/health` | 验证关停 |

**关键否证**：`with_kb_evidence.py` **不是**由 skill 链的任何一环调用的。
它是本批次**第 8 步**在链外手工执行的，用来做对照。

---

## 5. Task 2 —— skill 路径 vs API 路径（同一段文案、同一哈希）

同输入：`sha256 = de39890f0ce7c05beb4c93130710d98d71d2b2e22e1890c5dc874a93142d16bc`（两条路逐字一致）。

| 路径 | 实际调用的脚本 | 用了依据侧？ | 结论 |
|---|---|---|---|
| **skill 链**（内容审查总控 → 文案合规审查 → 审查裁决），按各 SKILL.md 点名的脚本站 | `review_text.py`（`:24` `scan_text`）→ `rule_engine.py` → `review_engine.py` | **否** | **PASS**（0.99 / issue_count 0） |
| skill 链 · 专项第 1 源 | `rule_engine.py`（5 条种子） | 否 | 0 候选 |
| skill 链 · 专项第 2 源 | `kb-content-review/scripts/review.py` | **是** | BLOCK（10 处） |
| **链外交接件**（没有任何 skill 点名它） | `with_kb_evidence.py` | **是** | BLOCK（10 处） |
| **API 路径** | `kb_api.py` `POST /review` →（`:247`）`with_kb_evidence.run()` → `review.py` → `decide()` | **是** | **BLOCK**（10 处 / evidence_complete 10/10） |

**API 路径逐字结果**（`curl … --data-binary @/tmp/batch12/copy.json`）：

```
state        = BLOCK
confidence   = 0.97
issue_count  = 10
content_version = de39890f0ce7c05beb4c93130710d98d71d2b2e22e1890c5dc874a93142d16bc
evidence     = {'findings': 10, 'source': '/Users/lute/.dsh/skills/kb-content-review/scripts/review.py'}
report_path  = kb/l7/reports/20261002-073125.review.md
next_owners  = ['内容提交方']
items: 10
   - P0 block W-1.18  措辞表达库 complete=True
   - P0 block W-1.1   措辞表达库 complete=True
   - P1 block W-1.31  措辞表达库 complete=True
   - P0 block W-1.53  措辞表达库 complete=True
   - P0 block W-1.33  措辞表达库 complete=True
   - P0 block W-1.13  措辞表达库 complete=True
   - P1 block W-1.41  措辞表达库 complete=True
   - P0 block W-1.8   措辞表达库 complete=True
   - P1 review W-1.35 措辞表达库 complete=True
   - P1 review W-1.11 措辞表达库 complete=True
```

**两条路是否一致：否。** skill 链 PASS ↔ API BLOCK，**结论相反**。

`/health` 佐证服务确为本库：`canonical_total=1242`，`patterns_loaded=7`。

### 5.1 API 路径的正确性核验（BLOCK 是不是**因为对的原因**）

是。逐条对齐 §1.2 的预期：

| 预期（库内 P0） | API 返回的条款号 | 一致 |
|---|---|---|
| H02 `increase milk supply` | W-1.18 | ✅ |
| H04 `doctor recommended` / `recommended by 100+ experts` | W-1.13, W-1.41 | ✅ |
| H05 `100% safe` | W-1.33 | ✅ |
| H06 `FDA approved` | W-1.8 | ✅ |
| H07 `pain-free` | W-1.53 | ✅ |
| H09 `mimics baby` | W-1.1, W-1.31 | ✅ |

10 条全部 `library=措辞表达库`、`evidence_complete=True`（六要素齐：库名 + 条款号 + anchor + source_sha256 + 逐字摘录 + 位置）。
`next_owners=['内容提交方']` 与 `内容审查总控/SKILL.md:25`（`BLOCK back to the submitter`）
及 `kb/l7/review-engine/core/review_engine.py:66-67`（`if decision == "BLOCK": return ["内容提交方"]`）一致。
裁决顺序也与 `审查裁决/SKILL.md:20`（`Confirmed P0 with locatable evidence … → BLOCK`）一致。
**不是偶然命中**：条款号与 H02/H04/H05/H06/H07/H09 六条 P0 一一对应。

### 5.2 服务关停（已执行）

```
$ lsof -nP -iTCP:8799 -sTCP:LISTEN     → (no listener on 8799 — shut down)
$ curl -s -m 5 http://127.0.0.1:8799/health → (connection refused — server down)
$ lsof -nP -iTCP:8787 -sTCP:LISTEN     → Python 90516 … TCP *:8787 (LISTEN)   # launchd 服务未受影响
```

用 8799（非 43120，也不占用 launchd 托管的 8787），用完已关停。

### 5.3 本批次在项目目录里**新增**的产物（如实披露）

运行 API 必然落盘（`kb_api.py:249` 硬编码 `write_report=True`，无开关可关）。
本批次**可逐字归属**的新增产物（判据：`content hash` 或 `trigger` 与本批次文案逐字一致）：

| 文件 | 由哪条命令产生 | 归属判据 |
|---|---|---|
| `kb/l7/reports/20261002-073125.md` | `curl POST /review` | `content hash = de39890f…` |
| `kb/l7/reports/20261002-073125.json` | 同上 | 同上 |
| `kb/l7/reports/20261002-073125.review.md`（21148 字节） | 同上 | 同上 |
| `kb/l7/runs/20261002-073126.json` | `with_kb_evidence.run()` 的 `run_record` | `trigger = "Momcozy S12 Pro Wearable Breast Pump…"`，`products=[…/20261002-073125.review.md]` |
| `kb/l7/runs/20261002-073409.json` | CLI `with_kb_evidence.py --text "Our pump has three modes"` | `trigger = "Our pump has three modes"`，`products=[]`（`write_report=False`） |
| `kb/l7/runs/20261002-073417.json` | CLI `with_kb_evidence.py`（计时复跑） | `trigger = "Momcozy S12 Pro Wearable…"`，`products=[]` |
| `kb/l7/reports/batch12-D-block-agent-path-20261002.md` | 本报告的写盘（交付物本身） | — |

**不归属本批次**（同窗口出现，但内容哈希是 `45a5aee74fe2b0a5847e57c57d15de440de97cf733737f791a8e88742c43ed78`，
送审文本是另一段更长的文案、以 `FDA approved and hospital grade, the Momcozy S12 Pro is 100% safe for baby…` 开头）：
`kb/l7/reports/20261002-0730*.{md,json,review.md}`、`…-0731*.{…}`、`…-0732*.{…}`、`…-0733*.{…}`、`…-0734*.{…}`
中的绝大多数，以及 `kb/l7/runs/` 里 trigger 以 `FDA approved and hospital grade…` 开头的十几条 `review_machine` 记录。
→ **同工作区有并发会话在跑**，这些不是本批次产生的。

**本报告未修改任何既有项目文件**；所有临时件在 `/tmp/batch12/`。
（`--dry-run` 的证据侧运行实测未落盘：`[dry-run] 未落盘。目标：…/20261002-073040.review.md`。）

> 一处**无法确定**：本批次 07:31:07 那次 CLI `with_kb_evidence.py` 的 `run_record` 文件
> （预期名 `kb/l7/runs/20261002-073107.json`）内容里 `trigger` 是并发会话的文案，不是本批次的。
> **推测**（非确认）：两边的 `run_id` 撞上了同一分钟秒，后写者覆盖了先写者。
> 不追查，不影响任何结论。

---

## 6. Task 3 —— 断点定位与最小修复建议

### 6.1 断点在哪（file:line）

**断点不是「依据侧算错了」，也不是「裁决侧判错了」。断点是：链自己点名的裁决入口
没有任何一行代码去取依据；唯一取依据的那一行代码，链里没有任何 skill 点名。**

**(a) 裁决侧入口根本不认识依据侧** —— `kb/l7/review-engine/core/review_text.py`

```
:20  def run(payload: dict, text: str) -> dict:
:22      gate_findings, gate_results = apply_product_fact_gates(payload, [{"text": text, "location": "text"}])
:23      payload["product_fact_gate"] = gate_results
:24      payload["risk_items"] = list(payload.get("risk_items", [])) + scan_text(
:25          text,
:26          product_line=payload.get("product_line", ""),
:27          channel=payload.get("channel", ""),
:28      ) + gate_findings
:29      return decide(payload)
```

全文件对依据侧的引用数 = **0**（`grep -n "evidence\|findings\|review_py\|REVIEW_PY\|with_kb" review_text.py`
只命中 `apply_product_fact_gates` / `gate_findings` 这些产品事实闸门的词）。
`risk_items` 只来自 `scan_text`（5 条种子）+ 产品事实闸门 → 本文案 **0 条** → `decide()` → **PASS**。

**(b) 裁决引擎只消费别人喂给它的条目** —— `kb/l7/review-engine/core/review_engine.py`

```
:130      items = _normalise_items(payload["risk_items"])          # 只读 payload
:131-134  confirmed_p0 = [... priority_tier=="P0" and status=="confirmed" and evidence_complete]
:136-139  blocking     = [... action=="block" and status=="confirmed" and evidence_complete]
:145-148  if confirmed_p0 or blocking: decision = "BLOCK"
:157-160  else: decision = "PASS"; reasons = ["no_known_blocking_or_review_risk"]
```

`decide()` 自述「it does not perform OCR, ASR, policy retrieval」—— **它不检索、也不应该检索**。
所以「把依据喂进来」必须发生在上游。上游是谁？就是 (a)。

**(c) 唯一接线的代码** —— `kb/l7/review-engine/core/with_kb_evidence.py`

```
:174      "risk_items": [_to_risk_item(f) for f in findings],     # ← 依据 → 契约
:179-180  if product_line_seed or channel: payload["risk_items"] += scan_text(...)   # 两源合并
:182      decision = decide(payload, report_url=None)
:143-149  if complete: item["evidence_id"] = ... ; item["evidence_url"] = ...        # 六要素齐才给 evidence_id
```

`with_kb_evidence` 的调用者（全仓 grep，排除 `_backups` / `_skill-backups`）：

| 调用点 | 是不是「skill 链」的一环 |
|---|---|
| `kb_api.py:208,212,218,247` | **API 路径** |
| `kb/l7/review-engine/core/with_kb_evidence.py:223`（自身 `main()`，CLI） | 手工执行 |
| `kb/l7/review-engine/tests/test_with_kb_evidence.py:26` | 单元测试 |
| `kb/l7/review-engine/core/evidence_cache.py:10`（仅 docstring 提及） | 无 |
| `kb/l7/skills/kb-content-review/scripts/review.py:1098,1247,1287`（仅注释/帮助文本） | 无 |

**没有任何 skill 的 `depends_on_engine` 登记了它**（`grep depends_on_engine kb/l7/registry/skills.yaml | grep -c with_kb_evidence` = **0**）。

**(d) 登记表也不认它** —— `kb/l7/registry/skills.yaml`

| 链上的 skill | registry id | depends_on_engine 里有没有 `with_kb_evidence.py` | 行号 |
|---|---|---|---|
| 内容审查总控 | `brand-content-review-agent` | **没有**（有 `review_text.py`、`review_engine.py`） | `kb/l7/registry/skills.yaml:616` |
| 文案合规审查 | `brand-text-compliance-review` | **没有**（有 `rule_engine.py` / `l5/matcher.py` / `rules.jsonl` / `l6/retriever.py`） | `kb/l7/registry/skills.yaml:667` |
| 审查裁决 | `brand-review-decision-engine` | **没有**（有 `review_engine.py`） | `kb/l7/registry/skills.yaml:769` |
| （链外）kb-review | `kb-review` | **没有**（有 `evidence_cache.py`，但没登记适配器本体） | `kb/l7/registry/skills.yaml:1127` |

**(e) 文档层：只有一处提到适配器，且不在本链上** —— 全仓 `grep -rn with_kb_evidence ~/.dsh/skills/` 结果：

| 文件:行 | 内容 |
|---|---|
| `~/.dsh/skills/kb-review/SKILL.md:110` | ② 裁决侧复用①的依据 → `with_kb_evidence.py --text … --findings-from …` |
| `~/.dsh/skills/kb-review/SKILL.md:159-160` | 「依据 → 裁决 的契约适配器」 |

`内容审查总控/SKILL.md`、`文案合规审查/SKILL.md`、`审查裁决/SKILL.md` 三个文件对
`with_kb_evidence` 的提及数 = **0**（`grep` 实测）。
而本批次被要求走的正是这三个。

**一句话**：「依据」与「裁决」之间的那根线**只存在于 `kb-review/SKILL.md` 的两行散文里**，
不在本链任何一个 skill 的正文里，也不在任何 skill 的 `depends_on_engine` 里，
更不在 `review_text.py` / `review_engine.py` 的任何一行代码里。
**是否接上，取决于 LLM 有没有读到 `kb-review` 那两行，并选择照做** —— 这正是「LLM 服从文档」，
不是确定性。

### 6.2 最小接线修复（确定性、不依赖 LLM 服从文档）

**核心思路：把「依据必须进入 `risk_items`」从散文变成入口脚本的默认行为。**

**修复点 1（必需，最小）—— 改 `kb/l7/review-engine/core/review_text.py:20-29`**

把 `run()` 改成：**先取依据（复用适配器），再合并种子候选与产品事实闸门，再 decide()**。

```python
# review_text.py（改后语义，伪代码；本批不实现）
def run(payload, text):
    payload = dict(payload)
    gate_findings, gate_results = apply_product_fact_gates(payload, [{"text": text, "location": "text"}])
    payload["product_fact_gate"] = gate_results
    # ① 依据侧：复用现成适配器，不重写映射
    ev_items = with_kb_evidence.evidence_risk_items(text)     # = [_to_risk_item(f) for f in findings]
    # ② 三源合并
    payload["risk_items"] = list(payload.get("risk_items", [])) + ev_items + scan_text(
        text, product_line=payload.get("product_line",""), channel=payload.get("channel","")
    ) + gate_findings
    return decide(payload)
```

要点：

1. **复用 `with_kb_evidence._to_risk_item`，不另写一份映射** —— 否则 §3 的实测会重演
   （手抄映射掉到 REVIEW）。建议把 `with_kb_evidence.py:112-150` 的 `_to_risk_item`
   与取依据的 `_evidence_findings`（`:72-109`）提为**公开函数**
   （如 `evidence_risk_items(text)`），供 `review_text.run()` 直接调用。
   `_to_risk_item` 已经是「六要素齐才给 `evidence_id`」的唯一真源，别复制。
2. **依据取不到时必须 fail-closed，不许静默 PASS**：`_evidence_findings` 返回 `(None, err)` 时
   （适配器不在位 / review.py 没吐 JSON），**不要**退回「只有种子规则」的老行为。
   改为让 `decide()` 走 `NEEDS_INPUT`（例如把 `input_manifest.status` 置为 `"failed"`，
   命中 `review_engine.py:120-128` 的 `manifest_status:failed` 分支），
   或在 payload 里补一个等价的 coverage 缺口。**「拿不到依据」≠「没问题」。**
3. **`--dry-run` / 缓存语义保持不变**：`review_text.py` 无 CLI 开关，保持 `_evidence_findings` 默认
   `write_report=False`（不落盘），并支持传入 `--findings-from` 复用同一 RUN 的依据，避免算两遍。

**修复点 2（必需，配套）—— 登记表补登 `kb/l7/registry/skills.yaml`**

在 `:616`（`brand-content-review-agent`）、`:667`（`brand-text-compliance-review`）、
`:769`（`brand-review-decision-engine`）的 `depends_on_engine` 里加入
`"l7/review-engine/core/with_kb_evidence.py"`；`:1127`（`kb-review`）同理
（它的正文 §2 已经点名这个文件，登记表却没登记 —— 按 `kb-review/SKILL.md:97-98`
「这五个文件就是注册表登记的那五个，两边必须一致」的口径，这是一条既存不一致）。

**修复点 3（建议，非必需）—— 三份 SKILL.md 的正文各加一行**

在 `内容审查总控/SKILL.md:23`、`文案合规审查/SKILL.md:29-31`、`审查裁决/SKILL.md:15`
把「文字冒烟走 `review_text.py`」「依据走 kb-content-review」改成明确写出
**「`review_text.py` 内部已接依据侧；要单独跑依据+裁决用 `with_kb_evidence.py`」**。

> 注意：**修复点 3 单独做等于没做** —— 它仍然是「LLM 服从文档」。
> 确定性的部分是**修复点 1**（代码默认行为）与**修复点 2**（登记表可被 `skill_conformance.py` 核）。

### 6.3 影响面（blast radius）

**会变的**

| 对象 | 会怎样变 |
|---|---|
| 所有走 `review_text.run()` 的判定 | 从「只看 5 条种子」变成「5 条种子 + 2036 条库内规则 + P0」。**原本 PASS 的会变 BLOCK/REVIEW**，包括本文案。 |
| `kb/l7/review-engine/tests/test_product_fact_integration.py:7,41-52`（`test_text_pipeline_uses_real_pending_queue`） | **实测：不会变红。** 该用例的文本是 `Our pump has three modes`；实测它命中库内 P0 = **0 条**，依据侧状态 = **拒答**、`findings = 0`。修复后依据侧**追加 0 条**，`decide()` 仍由产品事实闸门（`产品事实审批`）推到 `REVIEW` —— 与用例断言一致。（若将来该 payload 的文本改得更"脏"，另当别论。） |
| 同目录其余测试 | `test_review_engine.py` 直接 `decide()`，不改 `review_text` 则不受影响；`test_rule_engine.py` 不受影响；`test_with_kb_evidence.py` 不受影响（本次只把私有函数提为公开，行为不变）。 |
| 单次判定的**时延**（`/usr/bin/time -p` 实测，非估算） | 现状 `review_text.py`（裁决侧）= **real 2.23 s**（其中大部分是 `kbpy` 解释器启动）。依据侧 `review.py` = **real 3.51 s**。两者合并后的等价形态 `with_kb_evidence.py` = **real 4.02 s**（本文案）/ **4.27 s**（0 命中文本）。→ 修复后 `review_text.py` 的冒烟耗时将从 ~2 s 升到 ~4–6 s 量级，**用例耗时口径要重定**。 |
| 依赖面 | `review_text.py` 新增对 skill 装载位 `~/.dsh/skills/kb-content-review/scripts/review.py` 的**运行时依赖**（`with_kb_evidence.py:48-49` 的 `KB_CONTENT_REVIEW_PY`，默认 `Path.home()/".dsh/skills/…"`）。库内已有副本 `kb/l7/skills/kb-content-review/scripts/review.py`（与本批次实测所用 skill 副本 sha256 **逐字节相同**：`4fe7735c569fe12c0e65c503c0a10a96d7d02c0117c62e58a46e1564af9c3350`）—— 实现批次应决定默认指向哪一个，否则「库自洽」与「跟随装载位」会分叉。 |
| `kb/l7/registry/skills.yaml` 的三个 `depends_on_engine` | 新增一项后，`kb/l7/scripts/skill_conformance.py` 的「正文提到 = 登记在册」核对会从「缺登记」变「已登记」；`kb-check` 的体检表可能由黄转绿（**未实测**，本批未跑 `kb-check`）。 |

**不会变的**

- `decide()`（`review_engine.py:96-162`）的判定语义**不动** —— 本修复只改「谁把条目喂给它」。
- `kb/l4/canonical/*`、`kb/l3/candidates/rules.jsonl`、`kb/l5/p0_patterns.jsonl`、`kb_pipeline.py` **一律不动**。
- **API 路径行为不变**（`kb_api.py:247` 本来就调适配器，本修复只是把同一条路接到 skill 侧入口上）。
- 5 条种子规则（`kb/l7/review-engine/knowledge-base/seed-rules.json`）不动；
  `rule_engine.py` 的「非真源」标注（`:32-34`）不动。

### 6.4 未做（本批 = 只测不改）

本批次**未**修改 `review_text.py`、**未**修改 `skills.yaml`、**未**修改任何 SKILL.md、
**未**修改 `decide()`、**未**修改 `kb_pipeline.py`、**未**修改 `kb/l4/canonical/*`。
§6.2 只是提案，未落地。

---

## 7. 本批次无法确定的事（不与结论混写）

1. **L4 陈旧是否影响本结论** —— `freshness.py` 报 `L4 canonical/wording_entry.jsonl` 落后 2.9 天（退出码 3）。
   本次 BLOCK 的 10 条依据里，条款号来自 `kb/l3/candidates/rules.jsonl` 与 P0 匹配。
   「L4 陈旧是否会让条款号本身不可信」**本批次未判定**（需人裁，见 `freshness.py` 自己的提示）。
2. **`45a5aee7…` / `15–19 条 issue` 的那批 `review_machine` 记录来自谁** —— 其内容哈希与本批次文案不同，
   属**并发会话**。本报告只认领 `de39890f…` 的产物；未追查另一会话的身份与目的。
3. **手抄映射那条实测（REVIEW）是否在所有文案上成立** —— 只在本文案 10 条依据上测过，未做全量。
4. **修复后的回归基线** —— §6.3 里 `test_product_fact_integration.py` 一项已**实测**（文本命中库内 0 条 → 不会变红）。
   其余「哪些既有冒烟用例会从 PASS 翻成 BLOCK」**未做全量扫描** —— 实现批次应先跑一遍全量基线。
5. **`kb-check` 体检分变化** —— 未跑，纯属影响面提示。

---

## 8. 命令与产物清单（可复跑）

```bash
export PATH="$HOME/.dsh/bin:$PATH"
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
TEXT=$(cat /tmp/batch12/copy.txt)     # sha256 = de39890f0ce7c05beb4c93130710d98d71d2b2e22e1890c5dc874a93142d16bc

sh kb/kbpy l7/scripts/freshness.py                                              # exit 3（应拒答）
sh kb/kbpy l7/review-engine/core/review_text.py /tmp/batch12/payload_decision_only.json "$TEXT"   # PASS
sh kb/kbpy l7/review-engine/core/rule_engine.py "$TEXT"                          # []
sh kb/kbpy l7/skills/kb-content-review/scripts/review.py --kb-root "$PWD" --text "$TEXT" --json --dry-run --findings-out /tmp/batch12/findings.json   # BLOCK / 10
sh kb/kbpy l5/matcher.py --text "$TEXT" --json                                   # exit 1 / 6 条 P0
sh kb/kbpy l7/review-engine/core/review_engine.py /tmp/batch12/payload_decision_only.json         # PASS
sh kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "$TEXT"              # BLOCK / 10

KB_INTERP_OK=1 /usr/bin/python3 -m uvicorn kb_api:app --host 127.0.0.1 --port 8799 &   # API 路径
curl -s -X POST http://127.0.0.1:8799/review -H "Authorization: Bearer dsh-kb-dev-token" \
     -H 'Content-Type: application/json' --data-binary @/tmp/batch12/copy.json    # BLOCK / 10
# 用完已关停 8799（lsof 无监听、curl 拒绝连接）；8787 的 launchd 服务未动
```

临时件（全部在 `/tmp/batch12/`，未污染库）：
`copy.txt` / `copy.json` / `payload_decision_only.json` / `payload_control.json` /
`freshness.out` / `rule_engine.out` / `matcher.out` / `review_py.out` / `review_py_A.out` /
`review_text.out` / `review_engine.out` / `with_kb_evidence.out` / `findings.json` /
`api_review.json` / `reports_before.txt` / `reports_after.txt`
