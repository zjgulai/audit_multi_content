# kb-p0-check · 层操作手册（L5 P0 判定层）

> 本文件是 `kb-p0-check/SKILL.md` 的**详情页**（渐进式披露）。
> SKILL.md 只留「数据在哪 / 红线 / 写档档位指针」；判法与写档细目在这里。
> cwd 一律为**本次库根**（批次23 起由编排器按库根派生，写作占位符 `{kb_root}`；**不是**固定的 `~/.dsh/Momcozy知识库`）。

---

## 一、查询档：怎么判

```bash
cd "<本次库根>"
# ① 确定性匹配（给一段内容，看命中哪些 P0 模式）
kb/kbpy l5/matcher.py --text "<待判文本>" --json   # argparse：--text/--file/--json/--selftest
kb/kbpy l5/matcher.py --selftest                  # 自测：正例全命中、负例零误报（实测通过）
# ② 列 P0 模式清单
grep -c . kb/l5/p0_patterns.jsonl
# ⚠️ `kb/kbpy -` 不行（kbpy 只吃文件路径）。一次性片段用显式解释器：
KB_INTERP_OK=1 /usr/bin/python3 - <<'PY'
import json
for line in open('kb/l5/p0_patterns.jsonl', encoding='utf-8'):
    p = json.loads(line)
    print(p.get('anchor'), '|', p.get('authority'), '|units=', len(p.get('evidence_units') or []))
PY
```

**P0 的判据是「确定性命中」**：命中即 P0，**不需要语义推断**。
`p0_patterns.jsonl` 每条带 `anchor` + `authority` + `evidence_units[]`
（每个 unit 带 `unit_id` + `source_sha256`）—— **引用时必须带上它们**。

---

## 二、输出契约

```
是否 P0：是 / 否
命中模式：<anchor>（authority=<expert|...>）
命中片段：<逐字摘录>
证据单元：unit_id=<...> ｜ source_sha256=<...>
来源：kb/l5/p0_patterns.jsonl #<行号>
```

**「否」也要给出结论**：写「未命中任何 P0 模式」，并说明这**不等于**内容合规
（不命中 P0 只说明不是最高优先级，其余风险仍要按 `kb-review` 走）。

---

## 三、写档（只被 `kb-pipeline` 以层身份调用时走）

### 3.1 三条件（缺一不可，缺任一条只许停在查询档）

| # | 条件 | 怎么判 |
|---|---|---|
| ① | **由 kb-pipeline 以层身份调用** | 调用方是 `kb-pipeline`，且带 `RUN=<YYYYMMDD-HHMM>` 与「只跑 L5」 |
| ② | **`--apply`** | 不带即预演；预演只报「会写什么」，不落盘 |
| ③ | **人开闸** | 写档白名单见 `kb_pipeline.py` 的 `SYNC_ALLOWED`；越界要人点名 `--allow-beyond-policy` |

### 3.2 写档跑什么

**引擎清单不写在本节** —— 读 `kb/l7/registry/layers.yaml` **L5 层的 `engine`**（唯一真源）。
顺序按表（`kb/.work/l5_prep.py RUN` → `l5_export.py RUN`，另 `l5_bench.py` 性能验收）；
`RUN` 用调用方传进来的那个 run_id，**不要自己造 run_id**。

### 3.3 写档红线（L5 比别的层多一条）

- ★ **旧模式表必须人工归档**：本层 `write_mode: overwrite_with_archive`，但**归档动作不在脚本里**
  —— `p0_patterns.jsonl` 会被覆盖式重写，跑前必须先把旧表存成
  `kb/l5/runs/<RUN>.p0_patterns.superseded.jsonl`。**这是覆盖式写入的兜底缺口，不许省。**
- **基线类 FAIL 要登记、实质项 FAIL 要真修**：`l5_integrity.py` 的 6 项里，实质 4 项
  （pattern 回指 / 无凭空加词 / 版本纪律 / 离线）红了**必须真修**；基线 2 项
  （`frozen_layers` / `l3_append_only`）在活库上**必然 FAIL**，须逐项登记进
  `kb/l7/registry/l5-known-drift.yaml`，漏登记判红。**不许把实质项也当「判据过期」登记掉。**
- **幂等键是机器算的**：`pattern_id = 'p-' + sha1(f'{EXPORTER_VERSION}|{rule_id}')[:16]`
  —— 源不变则 id 不变；**不要手改 `pattern_id`**。
- **选取口径不许放宽**：`p_level=P0 ∧ rule_kind=atomic ∧ authority∈{expert,legal}`
  （+ `code_allowlist=[H06]`），实测 21 条 P0 → 入选 6 条；口径见 `kb/l5/registry/l5.json`。
- **跑完回闸门**：`kb/kbpy l7/scripts/l5_gate.py` 退出 0 才算本层收口。
