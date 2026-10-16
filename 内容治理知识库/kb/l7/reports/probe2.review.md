# 内容审查完整问题清单（run_id probe2）

结论：**PASS**｜问题数：0｜生成时间：2026-09-23 16:46:33

## 送审内容

```
it actually increased her milk supply
```

## 问题清单

## 检索轨迹

```json
{
 "p0": {
  "engine": "kb/l5/matcher.py",
  "exit_code": 0,
  "total_elapsed_ms": 60.38,
  "engine_elapsed_ms": 8.88,
  "hits": []
 },
 "rules": {
  "engine": "kb/l3/candidates/rules.jsonl",
  "kb_type_filter": null,
  "rules_scanned": 509,
  "hits": []
 },
 "units": {
  "engine": "kb/l6/retriever.py",
  "l6_mode": "vector_plus_bm25",
  "semantic_recall": true,
  "bm25_max": 16.4676,
  "cosine_max": 0.0,
  "used_vector": false,
  "no_semantic_annotation": null,
  "top_bm25": [
   {
    "source": "bm25_en",
    "unit_id": "5ff80f5422e3f9c107ce",
    "anchor": "#广告文案明细/recvuJYdObHV0W/命中片段",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "f52ba8f84062484d30e20a218dc4ce340ba19b7861786d2a38c15b8eab8f9acf",
    "raw_bm25": 16.4676,
    "excerpt": "H02:increasing milk supply / M03:hotseller"
   },
   {
    "source": "bm25_en",
    "unit_id": "7d7de1e9dacf7839fa03",
    "anchor": "#广告文案明细/recvuJYeGR6F4W/命中片段",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "9a80d8d6100f0ebc89b4316666e482f58bb390c4475c4560d2badb5e59346e1d",
    "raw_bm25": 11.1085,
    "excerpt": "H02:increases milk production"
   },
   {
    "source": "bm25_en",
    "unit_id": "c4b5b2972fef7b9231e1",
    "anchor": "#广告文案明细/recvuJYeGRdUud/命中片段",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "603f7455a4b757e519e3560bebe60b5ababb442844694d73a0728a24e29911c1",
    "raw_bm25": 11.1085,
    "excerpt": "H02:increases milk production"
   },
   {
    "source": "bm25_en",
    "unit_id": "576aa68d279717f05025",
    "anchor": "#品线内容边界规则库/recvuJP1dD7yNW/正则表达式",
    "table": "品线内容边界规则库",
    "kb_type": "wording",
    "source_sha256": "a4c587f8a609019660d8488c4663dde8e621fbad0cf2d610d4790355730579fa",
    "raw_bm25": 11.0227,
    "excerpt": "(increase|boost|double|triple|more)\\s+milk\\s+(supply|production|output), (increase|boost|double|triple)\\s+supply, increas\\w+\\s+milk\\s+(supply|production|output)"
   },
   {
    "source": "bm25_en",
    "unit_id": "b922ab4fccddce73bbe9",
    "anchor": "#广告文案明细/recvuJYdObHV0W/Primary Text",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "f52ba8f84062484d30e20a218dc4ce340ba19b7861786d2a38c15b8eab8f9acf",
    "raw_bm25": 10.379,
    "excerpt": "Momcozy Official | Mobile Style™ Wearable Breast Pump | Momcozy Hotseller - M6 Breast Milk Pump | Optimal Rhythm, Increasing Milk Supply | Comfort/ Discreet/ Po"
   }
  ],
  "vector_rows": [],
  "adopted": [
   {
    "source": "bm25_en",
    "unit_id": "5ff80f5422e3f9c107ce",
    "anchor": "#广告文案明细/recvuJYdObHV0W/命中片段",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "f52ba8f84062484d30e20a218dc4ce340ba19b7861786d2a38c15b8eab8f9acf",
    "raw_bm25": 16.4676,
    "excerpt": "H02:increasing milk supply / M03:hotseller",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_en",
    "unit_id": "7d7de1e9dacf7839fa03",
    "anchor": "#广告文案明细/recvuJYeGR6F4W/命中片段",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "9a80d8d6100f0ebc89b4316666e482f58bb390c4475c4560d2badb5e59346e1d",
    "raw_bm25": 11.1085,
    "excerpt": "H02:increases milk production",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_en",
    "unit_id": "c4b5b2972fef7b9231e1",
    "anchor": "#广告文案明细/recvuJYeGRdUud/命中片段",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "603f7455a4b757e519e3560bebe60b5ababb442844694d73a0728a24e29911c1",
    "raw_bm25": 11.1085,
    "excerpt": "H02:increases milk production",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_en",
    "unit_id": "576aa68d279717f05025",
    "anchor": "#品线内容边界规则库/recvuJP1dD7yNW/正则表达式",
    "table": "品线内容边界规则库",
    "kb_type": "wording",
    "source_sha256": "a4c587f8a609019660d8488c4663dde8e621fbad0cf2d610d4790355730579fa",
    "raw_bm25": 11.0227,
    "excerpt": "(increase|boost|double|triple|more)\\s+milk\\s+(supply|production|output), (increase|boost|double|triple)\\s+supply, increas\\w+\\s+milk\\s+(supply|production|output)",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_en",
    "unit_id": "b922ab4fccddce73bbe9",
    "anchor": "#广告文案明细/recvuJYdObHV0W/Primary Text",
    "table": "广告文案明细",
    "kb_type": "wording",
    "source_sha256": "f52ba8f84062484d30e20a218dc4ce340ba19b7861786d2a38c15b8eab8f9acf",
    "raw_bm25": 10.379,
    "excerpt": "Momcozy Official | Mobile Style™ Wearable Breast Pump | Momcozy Hotseller - M6 Breast Milk Pump | Optimal Rhythm, Increasing Milk Supply | Comfort/ Discreet/ Po",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   }
  ],
  "discarded": [],
  "gate": {
   "bm25_raw_min": 8.0,
   "vector_cosine_min": 0.6,
   "use_raw_scores_only": true,
   "why_not_rrf": "RRF 分恒为 1/(60+k)，实测 Top1 恒在 0.016393，A 组与 B 组看起来一样高，没有区分度，不能当门限",
   "why_single_threshold_not_enough": "实测 BM25 原始分在 A/B 两组有重叠（A 组最低 5.32 < B 组最高 10.02），所以门限只用于「够不够格当参考」，要成为「依据」还必须同时命中规则层",
   "measured": {
    "bm25_raw": {
     "A_group_min": 5.32,
     "A_group_median": 12.76,
     "B_group_median": 6.44,
     "B_group_max": 10.02,
     "source": "kb/l6/selftest.json → raw_score_comparison"
    },
    "cosine": {
     "A_group_min": 0.512,
     "A_group_median": 0.669,
     "B_group_median": 0.384,
     "B_group_max": 0.569,
     "source": "kb/l6/selftest.json → raw_score_comparison"
    }
   },
   "threshold_reasoning": "BM25 门限取 8.0：落在 A 组最低(5.32)与 B 组最高(10.02)之间、贴近两组中位之间，偏保守；余弦门限取 0.60：实测它是唯一能把 B 组全部挡在外面的取值（B 组最高 0.569），代价是 A 组丢 2 条；即便如此门限仍单独不可靠，必须叠加「同时命中规则层」才算依据",
   "below_threshold_label": "参考",
   "above_threshold_without_rule_hit": "仍只能标参考，不得作为依据",
   "coverage_bm25_min": 16.0,
   "coverage_reasoning": "PASS 必须建立在「知识库认识这个主题」之上，覆盖信号二选一：① 命中允许表述（安全词）规则；② 单元层 Top3 里有一条既被规则引用、BM25 原始分又 ≥ coverage_bm25_min(=16.0)。16.0 = 依据门限的 2 倍：实测 A 组中位 12.76 / 最高 23.16，B 组最高 10.02，取 16 能把实测 B 组全部挡在外面。覆盖信号不成立 → 拒答，不得输出 PASS。"
  }
 },
```
