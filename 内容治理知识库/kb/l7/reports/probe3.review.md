# 内容审查完整问题清单（run_id probe3）

结论：**PASS**｜问题数：0｜生成时间：2026-09-23 16:46:36

## 送审内容

```
能很好舒缓产后乳房酸胀，让她长时间吸奶也不会累、不会疼
```

## 问题清单

## 检索轨迹

```json
{
 "p0": {
  "engine": "kb/l5/matcher.py",
  "exit_code": 0,
  "total_elapsed_ms": 82.58,
  "engine_elapsed_ms": 10.237,
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
  "bm25_max": 16.7573,
  "cosine_max": 0.0,
  "used_vector": false,
  "no_semantic_annotation": null,
  "top_bm25": [
   {
    "source": "bm25_zh",
    "unit_id": "cda803e73f0da7ff15af",
    "anchor": "#专家修订汇总表/recvoAhrwbdEIN/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "1ef763e7224ece8792551dc0537db32a12910891e2c3a786d009e56aa4b589d4",
    "raw_bm25": 16.7573,
    "excerpt": "【前】夜间吸奶，尤其是凌晨 2～6 点 【后】夜间吸奶1次即可，时间建议为0-5点，主要原因是控制吸奶间隔，而非催乳素高峰 【原因】原因归因有误，夜间吸奶的主要原因是避免间隔时间过长，而非催乳素高峰"
   },
   {
    "source": "bm25_zh",
    "unit_id": "6bd4e7315823e42ef28d",
    "anchor": "#品线内容边界规则库/recvuJP1dDumuM/检测关键词",
    "table": "品线内容边界规则库",
    "kb_type": "wording",
    "source_sha256": "1c61c44b09ff77d121546f5ec15f74eba03afda2b77c1c77eb70b1e7525337fb",
    "raw_bm25": 15.6968,
    "excerpt": "safest, most safe, 100% safe, 100% painless, zero risk, guaranteed safe, perfect pump, 最安全, 唯一, 百分百安全, 零风险, 完美, fits all breast shapes, fits every breast, all b"
   },
   {
    "source": "bm25_zh",
    "unit_id": "1728b2fb9fc28762217f",
    "anchor": "#专家修订汇总表/recvoyJ6L9jvrX/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "04fd340a387946fa66351ebbad59e79f91a53564008173b104651485491f2321",
    "raw_bm25": 14.6099,
    "excerpt": "【前】文章整体核心命题 【后】建议删除该篇文章；如保留，需修正文章核心命题，区分亲喂与吸奶的差异，并明确本文适用场景为母婴分离情况 【原因】该命题本身存疑：对亲喂来讲可能成立，但吸奶不一定，产后初期吸奶不一定能很好地吸出初乳。且后续内容与已有吸奶器文章重复"
   },
   {
    "source": "bm25_zh",
    "unit_id": "42e34872db51ffd4a084",
    "anchor": "#专家修订汇总表/recvoyJ6L9l87q/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "7eb46630fd3848ad873000e13d48532dd9c44e673f718acd7bf99979b72c609e",
    "raw_bm25": 13.2652,
    "excerpt": "【前】偶尔一次影响不大， 【后】补充安全提示：长时间不排空乳房不仅会减少产奶，还可能导致乳汁淤积，增加乳腺炎风险，需引起重视 【原因】该表述未提示跳过喂奶/长时间不排空乳房可能引发乳腺炎的风险，存在安全隐患"
   },
   {
    "source": "bm25_zh",
    "unit_id": "baf32aa086e84deb489f",
    "anchor": "#专家修订汇总表/recvoAhrwbWyyz/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "8289d7742e936602b0f3af51b14b0d5566e7e5597efdd8b6f1a1514624d3f4bc",
    "raw_bm25": 10.715,
    "excerpt": "【前】策略四：侧躺喂奶，减少夜间起身 【后】将侧躺喂奶（C字形）调整为首要推荐策略，并补充说明：母乳喂养同床睡眠不会增加新生儿猝死综合征风险；同时保留具体操作要点 【原因】侧躺喂奶应作为首要推荐策略而非第四条；同时应补充C字形侧躺喂奶的安全性说明：母乳喂养同床睡眠并不会增加新生儿猝死综合征（SIDS）风险"
   }
  ],
  "vector_rows": [],
  "adopted": [
   {
    "source": "bm25_zh",
    "unit_id": "cda803e73f0da7ff15af",
    "anchor": "#专家修订汇总表/recvoAhrwbdEIN/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "1ef763e7224ece8792551dc0537db32a12910891e2c3a786d009e56aa4b589d4",
    "raw_bm25": 16.7573,
    "excerpt": "【前】夜间吸奶，尤其是凌晨 2～6 点 【后】夜间吸奶1次即可，时间建议为0-5点，主要原因是控制吸奶间隔，而非催乳素高峰 【原因】原因归因有误，夜间吸奶的主要原因是避免间隔时间过长，而非催乳素高峰",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_zh",
    "unit_id": "6bd4e7315823e42ef28d",
    "anchor": "#品线内容边界规则库/recvuJP1dDumuM/检测关键词",
    "table": "品线内容边界规则库",
    "kb_type": "wording",
    "source_sha256": "1c61c44b09ff77d121546f5ec15f74eba03afda2b77c1c77eb70b1e7525337fb",
    "raw_bm25": 15.6968,
    "excerpt": "safest, most safe, 100% safe, 100% painless, zero risk, guaranteed safe, perfect pump, 最安全, 唯一, 百分百安全, 零风险, 完美, fits all breast shapes, fits every breast, all b",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_zh",
    "unit_id": "1728b2fb9fc28762217f",
    "anchor": "#专家修订汇总表/recvoyJ6L9jvrX/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "04fd340a387946fa66351ebbad59e79f91a53564008173b104651485491f2321",
    "raw_bm25": 14.6099,
    "excerpt": "【前】文章整体核心命题 【后】建议删除该篇文章；如保留，需修正文章核心命题，区分亲喂与吸奶的差异，并明确本文适用场景为母婴分离情况 【原因】该命题本身存疑：对亲喂来讲可能成立，但吸奶不一定，产后初期吸奶不一定能很好地吸出初乳。且后续内容与已有吸奶器文章重复",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_zh",
    "unit_id": "42e34872db51ffd4a084",
    "anchor": "#专家修订汇总表/recvoyJ6L9l87q/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "7eb46630fd3848ad873000e13d48532dd9c44e673f718acd7bf99979b72c609e",
    "raw_bm25": 13.2652,
    "excerpt": "【前】偶尔一次影响不大， 【后】补充安全提示：长时间不排空乳房不仅会减少产奶，还可能导致乳汁淤积，增加乳腺炎风险，需引起重视 【原因】该表述未提示跳过喂奶/长时间不排空乳房可能引发乳腺炎的风险，存在安全隐患",
    "verdict": "≥ 门限",
    "reason": "原始分过门限 → 可作参考/待规则层确认"
   },
   {
    "source": "bm25_zh",
    "unit_id": "baf32aa086e84deb489f",
    "anchor": "#专家修订汇总表/recvoAhrwbWyyz/修订位置（原文引用）",
    "table": "专家修订汇总表",
    "kb_type": "internal_sample",
    "source_sha256": "8289d7742e936602b0f3af51b14b0d5566e7e5597efdd8b6f1a1514624d3f4bc",
    "raw_bm25": 10.715,
    "excerpt": "【前】策略四：侧躺喂奶，减少夜间起身 【后】将侧躺喂奶（C字形）调整为首要推荐策略，并补充说明：母乳喂养同床睡眠不会增加新生儿猝死综合征风险；同时保留具体操作要点 【原因】侧躺喂奶应作为首要推荐策略而非第四条；同时应补充C字形侧躺喂奶的安全性说明：母乳喂养同床睡眠并不会增加新生儿猝死综合征（SIDS）风险",
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

```
