# 批次12 · C 块 —— 「同一个 RUN」口径冲突：证据与选项（**只出材料，等人裁**）

**产出性质**：本文件**不改任何代码**。四件材料 = 代码级证据 / 甲乙两选项 / 改动量与风险 / 推荐。
**执行时间**：2026-10-02
**边界**：本块**未改** `kb_pipeline.py`、未改 `decide()`、未改任何落章机制。

---

## 1. DoD 原文与现况的对撞

**DoD 原文**：

> **同一个 RUN 内**，L0–L7 每层都留下落章，且 `skill_invocation_audit` 的 E2 判绿

**现况**：批 8/10 实际做的是**一层一个 RUN**。批 6 已证：多层共用一个 RUN 会让
`kb/l7/runs/<RUN>.json` 被最后一层覆盖、审计**只覆盖 1 层**。

⇒ 字面冲突：DoD 要「同一个 RUN 内逐层落章」，工程上却**必须**一层一 RUN。

---

## 2. 材料① · 代码级证据：为什么现在**必须**一层一 RUN

### 证据 1（决定性）—— 落章文件名就是 RUN，写入用 `"w"` 截断

`kb/l7/scripts/run_record.py:75-97`：

```python
def record(*, source, trigger, skills=None, commands=None, products=None,
           verdict="", human_involved=True, extra=None, run_id=None):
    """写一条 run 记录，返回 run_id。**只写 kb/l7/runs/**（不碰层数据）。"""
    ...
    rid = run_id or time.strftime("%Y%m%d-%H%M%S")
    rec = { "run_id": rid, "at": ..., "source": ..., "trigger": ...,
            "skills": _norm_list(skills), "commands": ..., "products": ...,
            "verdict": ..., "human_involved": ... }
    ...
    p = os.path.join(RUNS, rid + ".json")
    with open(p, "w", encoding="utf-8") as fh:      # ← 模式 "w"
        json.dump(rec, fh, ensure_ascii=False, indent=1)
```

**覆盖机制**：落章路径 `kb/l7/runs/<run_id>.json` **由 run_id 直接决定文件名**，
且以 `"w"`（截断重写）打开。⇒ 同一 RUN 被调两次（或两层共用），**后者整份覆盖前者**，
不是追加、不是合并。`kb/l7/runs/index.jsonl` 是追加的（`:94-95`），所以 index 会留下多行，
**但正本 `<run_id>.json` 只剩最后一层那一条**。

### 证据 2 —— 编排器自己知道自己会重复记账

`kb/l7/scripts/kb_pipeline.py:746` / `:899-901`：

```
:746  #   两次都走 run_record → `kb/l7/runs/index.jsonl` 一个 RUN 落 2 行
:899  help="驱动循环第 1 步专用：只过闸门 + 持锁/释放，**不写 kb/l7/runs/**。"
:901       "两次都记账会让 kb/l7/runs/index.jsonl 一个 RUN 落 2 行"
```

⇒ 编排器已经为「同一 RUN 被记两次」专门开了 `--gate-only` 开关来**规避**它。
这是**已知且已设防**的机制，不是猜测。

### 证据 3 —— E2 的判据是「按 RUN 找落章」，粒度就是 RUN

`kb/l7/scripts/skill_invocation_audit.py:34-35`（判据定义）：

```
E2 逐层无落章      **红**：本 run 涉及的层，在 `kb/<layer>/runs/` 里找不到
                   「属于本 RUN 且带 skill 落章」的记录 → 该层的「调了」无证据。
```

`:58-61`（落章契约）：

```
kb/<layer>/runs/<RUN>*.json 里至少一条记录满足：
  · `run_id` 以 `<RUN>` 开头，或 `pipeline_run_id == <RUN>`；
  · 带 `skill` / `skill_id` / `skills` 任一字段（顶层或 `extra` 内）
```

⇒ E2 的**查询键是 RUN**。它要求「层落章里的 run_id == 编排器记账的 RUN」。
若强行让多层共用一个 RUN，则**编排器记账文件** `kb/l7/runs/<RUN>.json` 会被最后一层覆盖，
E2 拿到的「②记账」那一侧就只剩一层的信息 —— 正是批 6 观察到的现象。

### 证据 4 —— `kb/l7/runs/` 是**双重身份**目录（一个额外陷阱）

`kb/l7/scripts/skill_invocation_audit.py:167-170`：

```
`kb/l7/runs/` 既是编排器的 run 记录目录，**又是 L7 那层的 runs 目录**（同一个路径），
不排掉就会拿「声称」当「证据」——L7 会永远自证通过（2026-09-30 实测到这个假阳）。
```

⇒ 任何「归组」方案都必须保留这个 `exclude`（`:172` / `:255`），否则 L7 自证。

---

## 3. 材料② · 两个选项

### 选项甲 —— 改 DoD 口径：「同一次工作流运行」= **一组 RUN**，用 `workflow_id` 归组

**不动现有审计**（E2 保持按 RUN 判）；DoD 的口径改成：
「同一次工作流运行中，L0–L6 每层各自留有落章，且这些 RUN 同属一个 `workflow_id`」。

- **要不要改代码**：**不必改审计**。可选（非必须）在编排器记账里加一个
  `workflow_id` 字段，让「哪几个 RUN 属于同一次运行」**可机器溯源**而不是靠文件名时间戳相邻。
- **改动量**：**极小**。若只在 DoD 措辞层面改（`workflow_id` 由人/编排器约定），
  则**零代码改动**；若要让 `workflow_id` 落进 `run_record.py` 的 `rec`，
  约 **+1 个可选参数、+1 行写入**（`kb/l7/scripts/run_record.py:75`/`:91`），
  另在 `kb_pipeline.py` 传参处加 1 处透传。
- **风险**：**低**。不动判据、不动落章路径、不动 E2 的查询键。
- **会不会破坏 E2 判绿**：**不会**。E2 仍按 RUN 逐层找落章，行为一字不变。
  唯一需要注意的是：DoD 措辞改了之后，**「同一次运行」的机器可判定性**取决于
  是否真落了 `workflow_id`；不落就是纯口径声明（可接受，但要如实标注为「人工约定」）。

### 选项乙 —— 改 `kb_pipeline` 支持 `workflow_id`，让多 RUN 归一个工作流号、审计按 workflow 聚合

- **要不要改代码**：**要，且要改审计**。
- **改动量**：**中等偏大**，至少四处：
  1. `kb/l7/scripts/run_record.py` —— 落章加 `workflow_id` 字段（+1 参数）
  2. `kb/l7/scripts/kb_pipeline.py` —— 生成并透传 `workflow_id`（驱动循环、各层记账）
  3. `kb/l7/scripts/skill_invocation_audit.py` —— **E2 的查询键要从 RUN 改成 workflow**：
     即把 `:34-35` 的「属于本 RUN」放宽成「属于本 workflow 的任一 RUN」，
     并相应改 `stamp_of()`（`:162`）与「②记账」的收集逻辑（`:134`）
  4. 落章契约（`:58-61`）要加一条：`workflow_id == <WF>` 也算命中
- **风险**：**中高**。具体三条：
  - **放宽查询键 = 放宽判据**。E2 从「逐 RUN 严判」变成「同 workflow 任一层有落章即算」，
    可能出现「某层这一轮其实没跑，但上一轮同一 workflow 的 RUN 让它绿了」——
    这正是 E1/E5 那类**假绿口子**的同族风险。要防它必须额外要求「workflow 内每层**至少一条**落章」，
    而那又回到「逐 RUN 找落章」的等价强度。
  - 触及 `kb/l7/runs/` 双重身份那个陷阱（材料①证据 4），改聚合逻辑时容易把 `exclude` 漏掉 → L7 自证假阳。
  - 触及审计脚本本身 —— 而审计是**判据的尺子**。改尺子比改被测物风险高一档。
- **会不会破坏 E2 判绿**：**很可能改其语义**。要么等价（白改），要么放宽（引入假绿风险）。

---

## 4. 材料③ · 推荐

**推荐选项甲**（改 DoD 口径 + 可选落 `workflow_id`），理由三条：

1. **冲突的根源在措辞，不在代码。** 证据 1–3 显示：一层一 RUN 不是权宜之计，
   而是「落章文件名 = RUN」这个**存储契约**的直接推论。要让多层共用一个 RUN 真正可行，
   得先把落章路径改成 `<RUN>/<layer>.json` 这种**分层命名** —— 那是一次**存储布局迁移**，
   要动 `run_record.py` + 全部层的落章写入 + E2 的 `stamp_of()` + 所有历史 `kb/*/runs/*.json` 的可读性。
   **成本远大于改一句 DoD 措辞，收益只是「字面一致」。**
2. **选项乙动的是「尺子」。** `skill_invocation_audit.py` 是判据实现，不是被测物。
   批次 6/10 的教训（E1 被 `--invoked` 清掉的假绿、E5 补的预演假绿）都是**判据口径**问题，
   每放宽一次查询键就开一个口子。选项乙要么等价白改、要么放宽引风险，**没有第三种结果**。
3. **选项甲能给出机器可溯源的替代物，且成本极低。** 落一个 `workflow_id`
   就能回答「这几个 RUN 是不是同一次运行」，而这正是 DoD 那句话真正想表达的东西 ——
   DoD 关心的是「**一次工作流运行是否逐层都调了 skill**」，不是「这些层是否共享一个时间戳字符串」。
   `workflow_id` 让这个意图**可机器核对**，且不改 E2。

**若人裁定走甲，建议的最小落地**（本批**不做**，留待开闸）：
- `run_record.py:75` 加可选参数 `workflow_id=None`，非空时写入 `rec["workflow_id"]`
- `kb_pipeline.py` 驱动循环生成一次 `workflow_id`（如 `wf-<起始RUN>`）并透传给每层记账
- **E2 一行不改**

---

## 5. 材料④ · 「L0–L7 每层」的口径该不该写成「7 层 + L7 跨层闸门」

**结论：该改。建议口径写「7 层 + L7 跨层闸门」。**

**证据**（`kb/l7/registry/layers.yaml:532-539`，L7 段原文）：

```yaml
- layer: L7
  skill: [kb-check]                  # 跨层统一闸门，不是 L7 的层主
  skill_write: false                 # kb-check 只报不改；要修走 kb-repair
  skill_note: >
    `kb-check` 是**跨层统一闸门**（注册表 layer 记「—」），不是 L7 的层主 ——
    所以「层 ↔ skill 双向一致」判据对它**豁免**，只要求「在注册表登记过 + 已装」。
    L7 是报告/注册表层，无写库引擎；`kb-repair` 是闸门红之后的修复入口（不在自动链路里）。
```

三条互相印证的要点：

1. **`skill_write: false`** —— L7 **没有写库引擎**，它不产出可落章的库内数据。
2. **`kb-check` 不是 L7 的层主** —— 注册表里它的 `layer` 记「—」，
   且「层 ↔ skill 双向一致」判据对它**已经豁免**。这说明**注册表自己就没把 L7 当普通层**。
3. **`kb/l7/runs/` 是编排器记账目录兼任 L7 runs 目录**（材料①证据 4）——
   若把 L7 当普通层要求落章，E2 会**永远自证通过**（audit 脚本自己记了这个假阳，
   并靠 `exclude` 排掉）。⇒ 「L0–L7 每层落章」这句对 L7 **在结构上无法有意义地成立**。

**与既有纪律一致**：`kb/l7/registry/write-gate.yaml` 明写
「**L7 永不进写档**（layers.yaml：报告/注册表层，无写库引擎）；本表任何条目都不许含 L7」，
且 `batch8-20261001` / `batch9-20261002` 两条凭据的 `layers` 都**只到 L6**。
⇒ 「7 层 + L7 跨层闸门」**不是新口径，是把已经在凭据与注册表里落地的口径写进 DoD**。

---

## 6. 本块交付边界

- **未改任何代码**（`kb_pipeline.py` / `run_record.py` / `skill_invocation_audit.py` 一字未动）
- 本文件是**材料**，等人裁；选项甲/乙**都未实施**
- 引用的所有 file:line 均已实际打开核对，非推测
