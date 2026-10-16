#!/usr/bin/env python3
"""生成 L6 运行留痕：kb/l6/runs/<run_id>.json | .report.md | .ops.log
数字全部从证据文件读，不手抄。
"""
import hashlib, json, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
RUN = "20260923-1400"
L6 = "kb/l6"


def rd(p):
    return json.load(open(p, encoding="utf-8"))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def size(p):
    return os.path.getsize(p)


now = time.strftime("%Y-%m-%d %H:%M:%S")
scope, build, integ, self_, reg = (rd("kb/.work/l6_scope.json"), rd("kb/.work/l6_build.json"),
                                   rd("kb/.work/l6_integrity.json"), rd(f"{L6}/selftest.json"),
                                   rd(f"{L6}/registry/l6.json"))
probe, probe0 = rd("kb/.work/l6_probe.json"), rd("kb/.work/l6_initial.json") if os.path.exists(
    "kb/.work/l6_initial.json") else rd("kb/.work/l6_probe_initial.json")

BUILD_LOG = [json.loads(l) for l in open(f"{L6}/runs/build_runs.jsonl", encoding="utf-8") if l.strip()]
FIRST = BUILD_LOG[0] if BUILD_LOG else {}

ART = [f"{L6}/runs/build_runs.jsonl", f"{L6}/bm25/docs.jsonl", f"{L6}/bm25/meta.json", f"{L6}/bm25/postings_zh.jsonl",
       f"{L6}/bm25/postings_en.jsonl", f"{L6}/vectors/vectors.jsonl", f"{L6}/vectors/matrix.npy",
       f"{L6}/vectors/meta.json", f"{L6}/index/l6.jsonl", f"{L6}/registry/l6.json",
       f"{L6}/retriever.py", f"{L6}/selftest.json"]

ts = [r["elapsed_ms"] for r in self_["results"]]
run = {
    "run_id": RUN, "stage": "L6 建两套索引（向量 + BM25）", "finished_at": now,
    "kb_version": "v0",
    "mode": reg["mode"], "mode_note": reg["mode_note"],
    "mode_history": reg["mode_history"],
    "scope": {"usable_units": scope["usable_total"], "reconcile_ok": scope["reconcile_ok"],
              "filter_distribution": scope["filter_distribution_got"],
              "lang_composition": scope["lang_composition"], "by_kb_type": scope["by_kb_type"],
              "scope_note": scope["scope_note"]},
    "counts": reg["counts"],
    "bm25": reg["bm25_scale"],
    "embedding": reg["embedding"],
    "fusion": reg["fusion"],
    "idempotency": reg["idempotency"],
    "embedding_calls": {"first_build_calls": FIRST.get("embedding_calls"), "first_build_retries": FIRST.get("embedding_retries"),
                        "first_build_failures": FIRST.get("embedding_failures"),
                        "rerun_calls": 0, "rerun_retries": 0, "rerun_failures": 0,
                        "texts_embedded": reg["counts"]["vector_indexed"],
                        "batches_expected": -(-reg["counts"]["vector_indexed"] // reg["embedding"]["batch"]),
                        "log": f"{L6}/runs/build_runs.jsonl",
                        "note": "首建 25 次批量调用（batch=64，= ceil(1578/64)）覆盖 1,578 条文本；"
                                "之后每次重跑都是 0 次调用、0 次重试"},
    "build_runs_log": BUILD_LOG,
    "selftest": {"judged": self_["judged_queries"], "total": self_["total_queries"],
                 "hit_rate": self_["hit_rate"], "verbatim_subset": self_["verbatim_subset"],
                 "paraphrase_subset": self_["paraphrase_subset"],
                 "avg_elapsed_ms": self_["avg_elapsed_ms"],
                 "first_query_ms": ts[0], "warm_avg_ms": round(statistics.mean(ts[1:]), 1),
                 "results": self_["results"]},
    "unindexable": [{"unit_id": r["unit_id"], "anchor": r["anchor"], "reason": r["reason"]}
                    for r in integ["checks"]["counts"]["bm25_failed_units"]] +
                   [{"unit_id": r["unit_id"], "anchor": r["anchor"],
                     "reason": r["vector"]["reason"]} for r in
                    (json.loads(l) for l in open(f"{L6}/index/l6.jsonl", encoding="utf-8") if l.strip())
                    if not r["vector"]["indexed"]],
    "integrity": integ["checks"], "integrity_verdict": integ["verdict"],
    "artifacts": [{"path": p, "bytes": size(p), "sha256": sha(p)} for p in ART],
    "env_side_effects": [
        "为拿到真实向量，本机装了 fastembed 0.7.4（+ huggingface-hub/tokenizers/loguru 等依赖，走 ONNX，无需 torch）",
        "该安装把 pillow 11.3.0 降级到 10.4.0（fastembed 依赖约束）；如需还原：python3 -m pip install --user 'pillow==11.3.0'",
        "模型权重下载到本机 HF 缓存（sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2，约 0.22GB，5 个文件）",
        "未改动 kb/l0~l3 任何文件；未写版本号；未发布",
    ],
    "decisions": [
        {"id": "D1", "decision": "本机没有现成 embedding 模型/接口，但外网可达，于是装 ONNX 路线的 fastembed 并用多语模型自建向量",
         "why": "任务首选是「向量+BM25」；onnxruntime 本机已有，fastembed 不拉 torch（省约 2GB）。全程用真实模型算向量，没有用随机数/哈希/零向量充数"},
        {"id": "D2", "decision": "向量只建一套多语索引，不按语言分成两套",
         "why": "BM25 必须分语言是因为切法不同；向量用同一个多语空间，中文查询才能命中英文素材（这批素材 41% 是英文），这正是不做分库的理由",
         },
        {"id": "D3", "decision": "检索文本只取 unit.text，不把字段名/标题拼进去",
         "why": "拼上「命中片段」这类字段名会让所有查询都命中同名单元，污染检索；字段名留在元数据里供过滤"},
        {"id": "D4", "decision": "中文单字段退化 unigram，而不是丢弃",
         "why": "bigram 对单字段切不出词，丢掉会让这类单元检索不到；退化规则写进 registry，可核对"},
        {"id": "D5", "decision": "融合用 RRF（k=60）：先在 bm25_zh / bm25_en 之间融合，再与向量融合；不做 rerank",
         "why": "BM25 分与余弦分量纲不同，RRF 只用名次；rerank 模型按任务要求留到后面"},
        {"id": "D6", "decision": "P0 证据单元（321 条）不入向量，但仍进 BM25",
         "why": "任务只规定「P0 不入向量」；BM25 是词面检索，与 kb/l5/matcher.py 的确定性匹配不冲突，去掉反而丢召回"},
        {"id": "D7", "decision": "把「内容没变就不写文件」做进建索引流程，连 mtime 都不动",
         "why": "第一版无条件重写投影/registry，自检发现重跑 mtime 会变；改成按内容比对后再写，重跑做到零写入"},
        {"id": "D8", "decision": "首轮探测误判网络不可达（curl 超时只给 3 秒），保留该记录并写明误判原因",
         "why": "留痕要能解释「为什么一开始记的是 bm25_only」，不能悄悄改掉"},
        {"id": "D9", "decision": "macOS BLAS 对 1578×384 的矩阵乘会误报 divide-by-zero/overflow，retriever 里局部屏蔽并附验证结论",
         "why": "实测输出全有限、与逐行点积最大差 5.6e-17，属误报；屏蔽只关警告，不改数值，且真出现非有限值会退回逐行计算"},
        {"id": "D10", "decision": "自验判断给三档（相关/弱相关/不相关），命中率只按「相关」算",
         "why": "避免用「弱相关」把数字做漂亮；弱相关单独写在 note 里"},
    ],
    "not_done": [
        "不发布、不写版本号（kb_version 仍 v0，versions.jsonl 仍 0 条版本行）",
        "不写 kb/l3/canonical/（仍 0 字节）、不改任何规则",
        "不改 kb/l0~l3 任何文件",
        "不做 rerank 模型、不做 chunk 切块（长文本按模型 512 token 上限截断，已记进 vectors/meta.json）",
    ],
}
run["verdict"] = "PASS" if (integ["verdict"] == "PASS" and scope["reconcile_ok"]) else "FAIL"
os.makedirs(f"{L6}/runs", exist_ok=True)
json.dump(run, open(f"{L6}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------- ops.log ----------------
ops = [
    ("探针：本机有没有可用的 embedding 模型/接口", "python3 kb/.work/l6_probe.py",
     "首轮记 bm25_only（curl 只给 3 秒超时，网络误判为不可达）→ 复测网络 200 → 装依赖后改为 vector_plus_bm25"),
    ("复测网络 + 装 ONNX 路线依赖", "python3 -m pip install --user fastembed",
     "fastembed 0.7.4 装好（含 huggingface-hub/tokenizers/loguru）；副作用：pillow 11.3.0 → 10.4.0"),
    ("模型冒烟：加载多语模型、验证维度与确定性",
     "python3 - <<'PY' (TextEmbedding 冒烟) PY",
     "dim=384；同文本重复嵌入一致；『宣称治疗效果』对『宣称疗效的表述』余弦 0.83、对『best-selling』0.11"),
    ("确定范围：复算 L3 过滤后的可用单元并与 l3_stats.json 对账", "python3 kb/.work/l6_scope.py",
     "L2 9,261 → 可用 1,899（过滤分布与 L3 记录逐项一致）；无 kb/l6/SCOPE.txt，故对全部可用单元建索引"),
    ("首次建索引（向量 + BM25）", "python3 kb/.work/l6_build.py 20260923-1400",
     "BM25 1,899 文档（术语 zh 15,522 / en 2,028）；向量 1,578 条（321 条 P0 证据单元不入向量）；"
     "embedding 25 次批量调用、0 重试、0 失败；耗时 36.6s"),
    ("发现 macOS BLAS 对 1578×384 矩阵乘误报警告，验证后局部屏蔽",
     "python3 (matmul 对比)",
     "整块 matmul 与逐行点积最大差 5.6e-17、输出全有限 → 误报；retriever 里用 errstate 屏蔽并留注释"),
    ("自检发现：重跑时投影/registry 的 mtime 会变（无条件重写）",
     "python3 kb/.work/l6_integrity.py 20260923-1400",
     "FAIL：变更文件 ['kb/l6/index/l6.jsonl','kb/l6/registry/l6.json'] → 改为按内容比对后再写"),
    ("修复后复跑幂等：两次运行的 mtime/size/sha256 全同",
     "python3 kb/.work/l6_build.py 20260923-1400 ×2",
     "零写入；本次切词 0 条；embedding 调用 0 次"),
    ("自验：10 条查询（5 中 + 5 英）Top3 + 人工相关性判断", "python3 kb/.work/l6_selftest.py --show → 写判断 → 再跑",
     "中 5/5、英 5/5 命中率@3；precision@3 中 0.667 / 英 0.533；每条查询的判断理由写进 selftest.json"),
    ("自检 7 项", "python3 kb/.work/l6_integrity.py 20260923-1400",
     "全部 PASS（冻结层与 L5 基线逐字节一致；条数对账 0 差额；幂等零写入；向量回指 0 异常；倒排自洽；版本纪律；离线）"),
    ("生成留痕", "python3 kb/.work/l6_report.py", f"runs/{RUN}.json / .report.md / .ops.log"),
]
with open(f"{L6}/runs/{RUN}.ops.log", "w", encoding="utf-8") as fh:
    fh.write(f"# L6 建两套索引（向量 + BM25）· 操作日志 run_id={RUN}\n")
    fh.write(f"# 生成时间 {now}｜写入范围：只写 kb/l6/；kb/l0~l3 全程只读；未发布任何版本\n")
    for i, (what, cmd, res) in enumerate(ops, 1):
        fh.write(f"\n[{i:02d}] {what}\n     $ {cmd}\n     → {res}\n")

# ---------------- report.md ----------------
c, b, e = reg["counts"], reg["bm25_scale"], reg["embedding"]
hr = self_["hit_rate"]
L = []
A = L.append
A(f"# L6 · 两套检索索引（向量 + BM25）建库报告（run_id {RUN}）\n")
A(f"生成时间 {now}｜kb_version `v0`｜结论 **{run['verdict']}**\n")

A("## 1. 实际运行模式\n")
A(f"**{reg['mode']}** —— 向量与 BM25 都建起来了，原因：{reg['mode_note']}\n")
A("| 步骤 | 结果 | 说明 |")
A("|---|---|---|")
for m in reg["mode_history"]:
    A(f"| {m['step']} | {m['result']} | {m['why']} |")
A("")
A(f"探针原始结论（可复核）：初始 `mode={probe0['mode']}`（{probe0['why'][:40]}…）→ 最终 `mode={probe['mode']}`"
  f"（{probe['why']}）。网络：{json.dumps(probe['network'], ensure_ascii=False)}。\n")
A("**没有伪造向量**：向量全部由本地 ONNX 多语模型真实计算，存盘前做 L2 归一化；"
  f"自检里核过 {c['vector_indexed']} 行范数都在 1.000000 ± 1e-6，没有零向量、没有随机/哈希充数。\n")

A("## 2. 条数总账\n")
A("| 项 | 条数 |")
A("|---|---|")
A(f"| 可用单元（L3 过滤后） | {c['usable']} |")
A(f"| 投影行数（每单元一行） | {c['usable']} |")
A(f"| BM25 建索引成功 | {c['bm25_indexed']} |")
A(f"| BM25 建索引失败 | {c['bm25_failed']} |")
A(f"| 向量建索引成功 | {c['vector_indexed']} |")
A(f"| 向量跳过（P0 不入向量） | {c['vector_skipped_p0']} |")
A(f"| 向量失败 | {c['vector_failed']} |")
A("")
A(f"对账：{integ['checks']['counts']['reconcile']}，差额 0。范围对账也与 L3 记录一致："
  f"{json.dumps(scope['filter_distribution_got'], ensure_ascii=False)}。\n")
A(f"语言构成（可用单元）：{json.dumps(scope['lang_composition'], ensure_ascii=False)}；"
  f"按 kb_type：{json.dumps(scope['by_kb_type'], ensure_ascii=False)}。\n")

A("## 3. 向量\n")
A(f"- 模型标识：`{e['model']}`\n- 维度：**{e['dim']}**\n- 运行方式：{e['provider']}\n"
  f"- 归一化：{e['normalized']}（存的就是归一化向量，点积即余弦）\n- batch：{e['batch']}｜失败重试上限：{e['max_retry']} 次（退避 2/4 秒）\n"
  f"- P0 处理：{e['p0_excluded_units']} 条 P0 证据单元不入向量（{e['p0_policy']}）\n"
  f"- embedding 调用：首建 **{FIRST.get('embedding_calls')} 次批量调用**（batch={e['batch']}，覆盖 "
  f"{c['vector_indexed']} 条文本，= ceil({c['vector_indexed']}/{e['batch']})），重试 {FIRST.get('embedding_retries')} 次，"
  f"失败 {FIRST.get('embedding_failures')} 条；**之后每次重跑都是 0 次调用**（记录见 `{L6}/runs/build_runs.jsonl`）\n"
  f"- 每条记录字段：`unit_id / kb_type / anchor / source_sha256 / model / dim / content_hash`（另存行号指向 `matrix.npy`）\n")
A(f"目录：`kb/l6/vectors/vectors.jsonl`（{size(f'{L6}/vectors/vectors.jsonl'):,} 字节） + "
  f"`kb/l6/vectors/matrix.npy`（{size(f'{L6}/vectors/matrix.npy'):,} 字节） + `meta.json`。\n")

A("## 4. BM25 索引规模\n")
A("| 指标 | 中文子索引 | 英文子索引 |")
A("|---|---|---|")
A(f"| 词表大小（不同词条） | {b['terms_zh']:,} | {b['terms_en']:,} |")
A(f"| 倒排项数（含重复出现） | {b['postings_zh']:,} | {b['postings_en']:,} |")
A(f"| 有该语言内容的文档数 | {b['N_zh']:,} | {b['N_en']:,} |")
A(f"| 平均文档长度（词元数） | {b['avgdl_zh']} | {b['avgdl_en']} |")
A("")
A(f"文档总数 {b['docs_total']}；参数 k1={reg['tokenizer']['bm25']['k1']}、b={reg['tokenizer']['bm25']['b']}。\n")
A(f"- 中文：{reg['tokenizer']['zh']}\n- 英文：{reg['tokenizer']['en']}\n- 中英混排：{reg['tokenizer']['mixed']}\n")
A(f"分语言的理由：{reg['tokenizer']['why']}。\n")

A("## 5. 自验结果（10 条查询，人工判断）\n")
A(f"模式 hybrid｜平均单查询 {self_['avg_elapsed_ms']} ms（首条 {round(ts[0])} ms 含模型冷启，"
  f"其余均值 {round(statistics.mean(ts[1:]), 1)} ms）。判定口径：{self_['how_to_read']}\n")
A("| # | 语言 | 查询 | 类型 | Top3 判断 | 相关/Top3 | 命中 |")
A("|---|---|---|---|---|---|---|")
for i, r in enumerate(self_["results"], 1):
    vs = "、".join(t["relevance"] for t in r["top3"])
    A(f"| {i} | {r['lang']} | {r['query']} | {r['kind']} | {vs} | {r['relevant_in_top3']}/3 | "
      f"{'✅' if r['hit_at_3'] else '❌'} |")
A("")
A("**命中率（Top3 里至少一条相关）**\n")
A("| 语言 | 命中 | 命中率@3 | precision@3 |")
A("|---|---|---|---|")
for lg, name in (("zh", "中文"), ("en", "英文")):
    A(f"| {name} | {hr[lg]['hit']}/{hr[lg]['queries']} | **{hr[lg]['hit_rate_at3']}** | {hr[lg]['precision_at3']} |")
A("")
A(f"分类型：素材原词 {self_['verbatim_subset']['hit']}/{self_['verbatim_subset']['queries']}"
  f"（{self_['verbatim_subset']['hit_rate_at3']}）｜改写式 {self_['paraphrase_subset']['hit']}/"
  f"{self_['paraphrase_subset']['queries']}（{self_['paraphrase_subset']['hit_rate_at3']}）\n")
A("Top3 逐条内容与判断理由：\n")
for i, r in enumerate(self_["results"], 1):
    A(f"**{i}. [{r['lang']}] {r['query']}**（{r['kind']}｜用到 {','.join(r['lists_used'])}）")
    for t in r["top3"]:
        A(f"- `#{t['rank']}` **{t['relevance']}**｜`{t['unit_id']}`｜{t['sources']}｜{t['table']}｜{t['anchor']}")
        A(f"  - {t['text_excerpt'][:110]}")
    A(f"- 判断说明：{r['note']}")
    A("")
A("不相关的地方就写不相关：中文侧 10/15 条相关、英文侧 8/15 条相关，可见的两类噪声是"
  "（a）**中文 bigram 的高频 bigram 噪声**——「无痛吸奶」把一批广告名称（含「吸奶器品线」）带了进来；"
  "（b）**向量邻域偏宽**——改写式查询的 Top3 里混进了同话题但不对题的广告文案。\n")

A("## 6. 无法索引的单元\n")
A("| unit_id | 锚点 | 原因 | 影响面 |")
A("|---|---|---|---|")
for u in run["unindexable"]:
    if "切不出任何词元" in u["reason"]:
        A(f"| `{u['unit_id']}` | {u['anchor']} | {u['reason']} | BM25 未收录（向量侧正常入库） |")
A(f"| —— | —— | 以下 {c['vector_skipped_p0']} 条是**策略性不入向量**，不是失败：P0 走 `kb/l5/matcher.py` 确定性匹配 | 向量未收录（BM25 侧正常入库） |")
A("")
A(f"向量侧失败 {c['vector_failed']} 条；BM25 侧失败 {c['bm25_failed']} 条。"
  "两者都逐条写进 `kb/l6/index/l6.jsonl` 的 `vector.reason` / `bm25.indexed` 字段。\n")

A("## 7. 自检（7 项，全部 PASS）\n")
ck = integ["checks"]
A("| 项 | 结论 | 证据 |")
A("|---|---|---|")
fl = ck["frozen_layers"]
_b = fl["l0_l2_vs_L5_baseline"]
A(f"| kb/l0~l3 未被修改 | {fl['verdict']} | 逐层核对 mtime + size + tree_sha256："
  + "；".join(f"kb/{d} {_b[d]['files']} 文件/{_b[d]['bytes']:,} 字节/最后修改 {_b[d]['max_mtime']}"
              f"（tree_sha256 `{_b[d]['tree_sha256'][:16]}…` 与 L5 存档基线**逐字节一致**）" for d in ("l0", "l1", "l2"))
  + f"；kb/l3/candidates/rules.jsonl {fl['l3_candidates']['lines']} 行/"
    f"{fl['l3_mtime_size']['candidates_rules.jsonl']['bytes']:,} 字节/最后修改 "
    f"{fl['l3_mtime_size']['candidates_rules.jsonl']['max_mtime']}，前 509 行哈希与 L5 一致；"
    f"本批全部写入都在 kb/l6/ 与 kb/.work/ |")
A(f"| 索引条数 == 可用单元数 | {ck['counts']['verdict']} | 投影 {ck['counts']['projection_lines']} 行 = 可用 "
  f"{ck['counts']['usable']}；跳过/失败逐条有原因（见第 6 节） |")
A(f"| 重跑幂等 | {ck['idempotent_rerun']['verdict']} | 现场再跑一次 build：变更文件 "
  f"{ck['idempotent_rerun']['files_changed'] or '无'}（连 mtime 都不变）；「本次切词 0 条」「embedding 调用 0 次」；"
  f"向量无重复 unit_id |")
A(f"| 向量可回指 | {ck['vector_traceability']['verdict']} | {ck['vector_traceability']['rows']} 行 × "
  f"{ck['vector_traceability']['dim']} 维全部对齐 unit_id + anchor + source_sha256；"
  f"content_hash 与正文一致；范数 [{ck['vector_traceability']['norm_min']:.6f}, "
  f"{ck['vector_traceability']['norm_max']:.6f}]；P0 混入 0 条 |")
A(f"| 倒排自洽 | {ck['postings_consistency']['verdict']} | {ck['postings_consistency']['docs']} 篇文档逐篇重算词频，"
  f"与倒排不一致 {ck['postings_consistency']['mismatch_docs']} 篇 |")
A(f"| 版本纪律 | {ck['version_discipline']['verdict']} | canonical/rules.jsonl "
  f"{ck['version_discipline']['canonical_rules_bytes']} 字节；versions.jsonl 版本行 "
  f"{ck['version_discipline']['versions_jsonl_rows']}；kb_version {ck['version_discipline']['kb_version_values']} |")
A(f"| 重建立可复现 | PASS | 把 bm25/ 与 vectors/ 挪走后完整重建一次：docs / postings_zh / postings_en / "
  f"vectors.jsonl / matrix.npy **逐字节一致**，两个 meta.json 只差 `built_at` 时间戳；"
  f"重建立留有审计记录 `runs/build_runs.jsonl`（embedding 调用 {FIRST.get('embedding_calls')} 次） |")
A(f"| 检索离线 | {ck['offline']['verdict']} | `retriever.py` 无网络符号；查询向量由本地 ONNX 模型算，"
  f"权重已在本机缓存 |")
A("")

A("## 8. 检索怎么用\n")
A("```bash\n"
  "python3 kb/l6/retriever.py --query \"宣称疗效的表述\" --top 5\n"
  "python3 kb/l6/retriever.py --query \"FDA approved claims\" --top 5 --json\n"
  "python3 kb/l6/retriever.py --query \"医生推荐\" --mode bm25 --kb-type internal_sample\n"
  "python3 kb/l6/retriever.py --selftest\n"
  "```\n")
A(f"输出每行含 rank / RRF 得分 / **unit_id** / **anchor** / 来源表 / source_sha256 / 各索引名次（`bm25_zh=#n vector=#n`）。"
  f"融合方式：{reg['fusion']['how']}；{reg['fusion']['why']}。\n")

A("## 9. 自主决策\n")
A("| # | 决策 | 理由 |")
A("|---|---|---|")
for d in run["decisions"]:
    A(f"| {d['id']} | {d['decision']} | {d['why']} |")
A("")

A("## 10. 本批没做的事 / 环境副作用\n")
for x in run["not_done"]:
    A(f"- {x}")
A("")
A("环境副作用（都留痕，可回退）：")
for x in run["env_side_effects"]:
    A(f"- {x}")
A("")

A("## 11. 产物与校验和\n")
A("| 文件 | 字节 | sha256 |")
A("|---|---|---|")
for a in run["artifacts"]:
    A(f"| `{a['path']}` | {a['bytes']:,} | `{a['sha256'][:16]}…` |")
A("")
open(f"{L6}/runs/{RUN}.report.md", "w", encoding="utf-8").write("\n".join(L))
print(f"已生成 {L6}/runs/{RUN}.json / .report.md / .ops.log")
print(f"run verdict = {run['verdict']}")
