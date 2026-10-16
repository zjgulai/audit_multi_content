# Batch 12 · B 块 · 阻断时延实测：一行「帮我审一下」到底要多久

**结论（先说）**：**两条路都 PASS，warm P50 均为 1.2–1.6 秒，距 60 s 门槛约 40 倍余量。**
主导段不是 `decide()`（0.0012 s），也不是模型加载（本次输入根本没走向量路），
而是**每次调用都要重新构建的 BM25 倒排索引（中位数 928 ms）**；且**确认不存在任何跨调用常驻缓存**
—— 证据是「同进程内连跑两次，第二次没有变快（0.987×）」。

- 测量对象：确定性内核（CLI 适配器 / HTTP API），**不含 agent 与 LLM 推断**（见 §9 边界）
- 测量日期：2026-10-02 07:29–07:39（本地）
- 未修改任何工程文件；所有插桩脚本在 `/tmp/kb12/`（见 §9）

---

## 0. 输入（两次路径全程同一条，逐字固定）

```
FDA approved and hospital grade, the Momcozy S12 Pro is 100% safe for baby and completely pain-free. It mimics your baby's natural nursing rhythm and is clinically proven to increase milk supply in 3 days. The #1 best selling breast pump on Amazon, now with a doctor recommended flange that prevents clogged ducts and cures sore nipples.
```

- 字节数 **337**；`sha256 = 45a5aee74fe2b0a5847e57c57d15de440de97cf733737f791a8e88742c43ed78`
- 结论稳定：`BLOCK`，`evidence.findings = 12`，`issue_count = 15`（12 条库内依据 + 3 条 5 条种子规则候选）
- CLI 与 API 两路返回的 `content_version` 一致（`45a5aee74fe2`，即上面 sha256 前 12 位）

命令（CLI，逐次同一形状）：

```
/usr/bin/time -p python3 kb/l7/review-engine/core/with_kb_evidence.py \
  --text "<above>" --channel "amazon" --product-line "吸奶器" --product-line-seed "吸奶器" --json
```

> `--product-line-seed` 是给 5 条种子规则扫描器（`rule_engine.scan_text`）的词表原样值；
> `with_kb_evidence.py` 的 `--product-line`（:212）只进裁决 payload，不喂扫描器。

---

## 1. PASS / FAIL 判定

| 路径 | cold | warm P50 | warm MAX | n(warm) | 判据 warm P50 ≤ 60 s |
|---|---|---|---|---|---|
| CLI `with_kb_evidence.py` | **1.220 s** | **1.235 s** | **1.330 s** | 8 | **PASS** |
| API `POST /review` | **2.017 s** | **1.646 s** | **2.042 s** | 8 | **PASS** |

- **P50 怎么算的**：中位数（`statistics.median`，偶数样本取中间两值均值）。**n = 8，样本极少**，
  这里只报中位数与最大值，不声称任何统计置信度、不报 P95/P99。
- API 另有一组 21 次 warm 合并样本（§4 三组序列）：**P50 = 1.475 s，MAX = 2.042 s**。
- CLI 另有 2 组早于本组的序列（§2），warm P50 分别 1.480 s / 1.685 s，MAX 最大 1.88 s，
  **全部远低于 60 s**，判定不因取哪一组而改变。

---

## 2. Task 1 · CLI 路径逐次墙钟

`/usr/bin/time -p` 的 `real`，单次一行。三组序列分开列，因为**本库在我测量期间被另一个会话改过**（§6）。

**序列 C（主序列）** —— KB 指纹在每次运行前后完全一致（guard `0d48111f…`），运行窗 07:33:17–07:33:28：

| run | 1 (cold) | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| real (s) | 1.22 | 1.23 | 1.23 | 1.28 | 1.32 | 1.24 | 1.33 | 1.22 |

n=8 · min 1.220 · **P50 1.235** · max 1.330

**序列 A**（07:29:39–48，未加 guard）：1.30 / 1.47 / 1.50 / 1.49 / 1.56 / 1.35 → P50 1.480 · max 1.56
**序列 B**（07:32:51–59，未加 guard，**KB 在该序列内被改**：run1 findings=16，run2–6 findings=12）：
1.63 / 1.82 / 1.88 / 1.74 / 1.45 / 1.19 → P50 1.685 · max 1.88

> 序列 A 的 run 1（1.30 s）与序列 C 的 run 1（1.22 s）就是 CLI 的 cold：**cold 并不比 warm 慢**
> （C 组 cold 1.220 < warm P50 1.235，差 −0.015 s）。这不是"冷启动很快"，是**CLI 没有 warm 态**（§5）。

---

## 3. Task 1 · 分段实测表（CLI 路径）

三段插桩来源：适配器进程内包装、review.py 进程内包装、retriever 的 `BM25` 计时子类（技术见 §9）。
每个段跑 **3 次**（表格里是 3 次原值 + 中位数）。

| 段 | 怎么量的 | rep1 | rep2 | rep3 | 中位数 |
|---|---|---|---|---|---|
| `python3 -c pass` 解释器基线 | `/usr/bin/time -p` real | — | — | — | **0.030 s** |
| 适配器进程启动（`--help` 墙钟） | `/usr/bin/time -p` real | 0.06 | 0.06 | 0.06 | **0.06 s** |
| 适配器显式 import 合计（stdlib+3 模块） | `perf_counter` | 27.1 | 25.9 | 26.3 | **26.3 ms** |
| 适配器模块导入（driver 内 `exec_module`） | `perf_counter` | 21.2 | 26.5 | 13.7 | **21.2 ms** |
| **`_evidence_findings()` = review.py 子进程（整段）** | 包装真实函数 | 1445.2 | 1325.2 | 1108.3 | **1325.2 ms** |
| ├ review.py 模块 import | `perf_counter` | 10.5 | 20.9 | 12.0 | **12.0 ms** |
| ├ `load_registry()`（l7.json） | 包装真实函数 | 0.2 | 0.4 | 0.2 | **0.2 ms** |
| ├ `load_rules()`（509 条规则 + L4 条款号 join） | 包装真实函数 | 40.2 | 73.8 | 44.0 | **44.0 ms** |
| ├ `layer_p0()` = **matcher.py 子进程**（第三个解释器） | 包装真实函数 | 83.4 | 81.8 | 59.6 | **81.8 ms** |
| │ └ 其中 matcher 自己报的引擎耗时 | review.py trace | 9.13* | 10.70* | 8.63* | ~9.1 ms |
| ├ `layer_rules()`（1018 行库 → 本次扫 509 条） | 包装真实函数 | 26.3 | 44.9 | 27.0 | **27.0 ms** |
| ├ **`layer_units()`（BM25 召回，整段）** | 包装真实函数 | 1009.3 | 1334.9 | 1217.0 | **1217.0 ms** |
| │ ├ `exec_module(retriever.py)`（每次都重跑） | loader 代理 | 0.6 | 0.7 | 0.7 | **0.7 ms** |
| │ ├ **`BM25()` 构造 = 读倒排索引** | 计时子类 | 1341.1 | 928.0 | 860.4 | **928.0 ms** |
| │ ├ `BM25.search(text)` | 计时子类 | 31.4 | 20.1 | 25.4 | **25.4 ms** |
| │ ├ `kb/l6/registry/l6.json` 读盘 | `perf_counter` | 0.3 | 0.4 | 0.2 | **0.3 ms** |
| │ └ 余项（postings_en 读盘 + top-N 组装） | 差值推导 | 46.1 | 36.6 | 36.2 | **36.6 ms** |
| ├ `review()` 体内其余（分类/去重/`resolve_excerpt`/覆盖信号） | 差值推导 | 45.2 | 45.4 | 39.9 | **45.2 ms** |
| `scan_text()`（5 条种子规则） | 包装真实函数 | 1.2 | 0.7 | 0.9 | **0.9 ms** |
| **`decide()`（裁决引擎，`review_engine.py:96`）** | 包装真实函数 | 1.3 | 1.1 | 1.2 | **1.2 ms** |
| `run_record` + 组装（差值推导） | 差值推导 | 2.8 | 1.4 | 1.5 | **1.5 ms** |

\* matcher 引擎耗时**不是**本次 3-rep driver 的输出（那个 driver 只报 `layer_p0` 总耗时）：
9.091 取自 `cli_run_1.json`、10.704 取自 `cli_run_2.json`、8.628 取自 `drv_sub_segments.py` 的另一次运行
（对应 `evidence_meta.trace.p0.engine_elapsed_ms`）。
`run_record` + 组装行 = `run_total − evidence_subprocess − scan_text − decide`（差值推导，非直接测量）。

**占比重算**（中位数口径，跨测量集，标注为推导值）：

- `_evidence_findings()`（子进程） / `run()` 总耗时 = **1325.2 / 1328.4 = 99.76%** → 适配器自己只占 0.24%
- `decide()` / `run()` 总耗时 = **1.2 / 1328.4 = 0.09%**
- **`BM25()` 构造 / CLI 端到端（P50 1.235 s）= 928.0 / 1235 = 75.1%**
- `layer_units()` / `review()` 体内（同 driver 中位数）= 1217.0 / 1387.7 = **87.7%**
- `BM25()` 构造 / `layer_units()`（同 driver 中位数）= 928.0 / 985.8 = **94.1%**

> 三轮之间 `BM25()` 从 860 ms 摆到 1341 ms（±24%），因为**另有会话在同一台机器上写库**（§6）。
> 所有比值都按中位数算，别把单轮比值当精度。

**导入明细**（`python3 -X importtime`，cumulative 列前几名，单位 ms）：

- 适配器（101 行）：`argparse` 6.523 · `re` 5.376 · `subprocess` 5.198 · `site` 4.323 · `review_engine` 2.462
- review.py（87 行）：`argparse` 9.912 · `re` 8.091 · `subprocess` 5.553 · `site` 4.716 · `functools` 4.192

> 方法说明：`-X importtime` 的 cumulative 列**含嵌套的重复计入**，因此这里**不求和**，只做单点定位；
> 求和口径用上面的 `perf_counter` 显式 import（适配器 26.3 ms / review.py 20.8 ms，均为 3 次中位数）。

---

## 4. Task 2 · API 路径逐次墙钟

启动（照 `kb_api.py:8-11` 的启动方式，只换端口 → 8137，避开在用的 43120 与生产 8787）：

```
nohup python3 -m uvicorn kb_api:app --host 127.0.0.1 --port 8137 >> /tmp/kb12/api2.log 2>&1 &
```

- 就绪：`GET /health` 首次返回 200 用时 **0.632 s**（进程启动 + `_load_canonical()` 1242 条 + `compile_patterns()` 7 条模式）
- `/health` 实测：`{"ok":true,"canonical_total":1242,"patterns_loaded":7,"auth":"Bearer token"}`

请求（`ReviewReq` 字段按 `kb_api.py:225-231` 构造，`Authorization: Bearer dsh-kb-dev-token`）：

```
curl -s -o /tmp/kb12/apicold_run_N.json -w '%{time_total} %{http_code} %{time_starttransfer}' \
  -X POST http://127.0.0.1:8137/review -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dsh-kb-dev-token' --data-binary @/tmp/kb12/req.json
```

**序列 C（主序列，全新 server，07:34:06–07:34:25）** —— guard 每次都 before==after：

| run | 1 **COLD** | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| `time_total` (s) | **2.017** | 1.626 | 1.551 | 1.666 | 1.871 | 2.042 | 1.823 | 1.398 | 1.337 |

warm(n=8) min 1.337 · **P50 1.646** · **MAX 2.042**；全部 `http_code=200`，`findings=12`，状态 `BLOCK`。

**序列 B**（07:33:34–47，guard 0d48111f…）：1.635 / 1.373 / 1.355 / 1.475 / 1.390 / 1.343 / 1.432 / 1.371
→ P50 1.381 · MAX 1.635
**序列 A**（07:30:57–07:31:06，**server 的第一次 `/review` 就是这一组的 cold**）：
1.794 / 1.381 / 1.870 / 1.931 / 1.528 / 1.475 → cold 1.794 · warm P50 1.528 · MAX 1.931

- HTTP 自身开销可忽略：`time_total − time_starttransfer` = 0.0001–0.0004 s（连接 `time_connect` 0.0003–0.0005 s）
- **服务已在 07:39 前关闭并确认停止**：`lsof -iTCP:8137 -sTCP:LISTEN` 无输出、`curl` 返回 `http=000`、
  `pgrep -f "port 8137"` 无匹配。**生产实例 8787（PID 90516，已跑 1 天 19 小时，非我启动）未被触碰。**

---

## 5. 关键问题：时间花在哪、加载是不是每次都重做

### 5.1 主导段 = BM25 倒排索引每次重建

- `retriever.BM25.__init__`（`kb/l6/retriever.py:254-262`）每次构造都全量读盘：
  `docs.jsonl` **15,514,809 B / 4,261 docs**、`postings_zh.jsonl` **8,828,002 B / 102,547 terms**、
  `postings_en.jsonl` **8,131,322 B / 31,430 terms**（合计读 ~32 MB JSON→Python 对象）。
- 中位数 **928 ms**，占 CLI 端到端 **75.1%**；`layer_units()` 里 **94.1%** 是它。
- `BM25.search()` 只花 **25.4 ms**；也就是说**索引构建是检索的 36 倍**。
- `decide()` **1.2 ms**，占 0.09% —— 裁决引擎不是瓶颈。

### 5.2 加载**确实**每次调用重做，而且**连进程内都不缓存**

| 证据 | 实测 |
|---|---|
| CLI cold vs warm 差 | cold 1.220 s vs warm P50 1.235 s → **−0.015 s（cold 更快）**，说明不存在"跑热了会变快" |
| **同进程内连跑两次**（`review()` 直接调 2 次，同文本） | call1 **1558.8 ms** → call2 **1578.9 ms**，加速比 **0.987×**（第二次没有变快） |
| 每次 CLI 调用起几个解释器 | **3 个**：适配器 + `review.py` 子进程 + `matcher.py` 孙进程 |
| 为什么进程内也不缓存 | `layer_units()` 每次 `spec.loader.exec_module(RT)` 重新执行 retriever.py，再 `RT.BM25()` 重建索引；没有任何模块级索引单例 |
| 唯一的缓存 | `kb_api._ADAPTER`（`kb_api.py:212-222`）只缓存**适配器模块对象**，不缓存任何索引；`evidence_cache`（`--findings-from`）是**可选**的，两条路默认都没用 |

**API 侧的直接证据（进程表采样，50 ms 一次）**：

- 请求前后：server **没有任何子进程**
- 单次请求内：出现 **1 个 `review.py` 子进程**（`ppid = server PID 11281`），存活约 1.0–1.1 s
- 连发 2 次请求：观测到 **2 个互不相同的 PID**，各自还带 1 个 `matcher.py` 孙进程：
  `15320 (ppid 11281) → 15322` 与 `15444 (ppid 11281) → 15448`
- 结论：**server 常驻只省掉了 `_load_canonical()` + `compile_patterns()` 的 0.632 s 启动开销；
  每次 `/review` 仍然起新进程、重读 rules.jsonl + L4 canonical + BM25 索引。**

### 5.3 server 日志里有没有重复加载行？——**没有，因为子进程 stderr 被吞了**

`/tmp/kb12/api2.log` 全文（9 次请求）：

```
INFO:     Started server process [20056]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8137 (Press CTRL+C to quit)
INFO:     127.0.0.1:62762 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:62764 - "POST /review HTTP/1.1" 200 OK
...（其余 8 行同为 POST /review 200 OK）
```

`grep -c "BM25\|load\|model\|index" api2.log` = **0**。原因不是"没重复加载"，而是
`with_kb_evidence.py:90` 用 `subprocess.run(..., capture_output=True)` 把子进程 stdout/stderr 全收走了，
review.py 的 `[fix] 条款号…` / `[review] 报告落盘通道…` 这类行根本到不了 server 日志。
**所以"日志里没看到重复加载"不能当作没重复加载的证据**；上面的进程采样才是证据。

### 5.4 模型（embedding）本轮**不在关键路径上**

`layer_units()` 只在 `bm25_max < gate.bm25_raw_min(8.0)` 时才加载向量（`review.py:307-309`）。
本次输入 `bm25_max = 76.8889`，**`used_vector = false`**，235 MB 的 ONNX 模型全程没加载。

单独实测"若门限被击穿会多花多少"（**不在本次关键路径上，仅供参考**）：

| 段 | 实测 |
|---|---|
| `Vectors()` 构造（`matrix.npy` 39,742,592 B + `vectors.jsonl` 17,624,279 B / 25,874 行） | 207.6 ms |
| `fastembed.TextEmbedding(...)` 模型加载（权重缓存 `/Users/lute/.dsh/models/fastembed`，240 MB） | **1,035.5 ms** |
| `Vectors.search()` | 57.8 ms |

即：**若走向量路，端到端还要再加约 1.30 s**（总计 ~2.5 s），仍然远低于 60 s。

### 5.5 API 比 CLI 慢的那 ~0.4 s = 报告写盘（CLI 根本不写报告）

| 段 | 实测（同函数、目标目录改到 `/tmp`） |
|---|---|
| `write_report()`（node 明文通道写 + 读回校验） | **320.1 ms** |
| `write_report_memory()`（再写 `.md` + `.json` 两份） | **126.7 ms** |
| 合计 | **446.8 ms** |

这解释了 API warm（P50 1.646 s）≈ CLI 子进程（~1.1–1.3 s）+ 0.45 s。

> **顺带一个契约问题（不是时延问题）**：`with_kb_evidence.py:220` 定义了 `--dry-run`，
> 但 `:223-225` 调 `run()` 时**从不传 `write_report`**，`run()` 默认 `False`（`:154`），
> 于是 `:88-89` **永远**给 review.py 追加 `--dry-run`。
> → **CLI 路径永远不产报告文件**，只吐 stdout JSON。DoD 若要求"产出一份报告"，CLI 这一路现在不满足。

---

## 6. 测量期间本库被另一个会话改过（必须说明的污染）

- `kb/l3/candidates/rules.jsonl` 在 **07:32** 被改写（我 07:31 读到 2,778,734 B / mtime 07:32，
  07:36:48 再读为 **5,762,300 B** / mtime 仍是 07:32，即同一分钟内又长过一次）。
- 直接后果：**序列 B 内部结论漂移** —— run1 `findings=16 / issue_count=19`，run2–6 `findings=12 / issue_count=15`。
- 另有平行会话在写 `kb/l7/reports/batch12-C-…md`、`batch12-D-…md`，并在跑 `daily_health` / `l0_daily` /
  `pipeline_sync`（`kb/l7/runs/index.jsonl` 里能看到 `source=daily_health|l0_daily|pipeline_sync` 的记录）。
- 因此**主结论只取 guard 校验通过的两组序列**（CLI 序列 C、API 序列 B/C）：
  每次运行前后对 `rules.jsonl / p0_patterns.jsonl / bm25/* / l7.json / l6.json / l4/canonical/*.jsonl`
  取 sha256 汇总指纹，**before == after 才计入**。三组序列共 **25 次**运行（CLI C 8 + API B 8 + API C 9）
  全部 before==after，且当时指纹均为 `0d48111f1886962f020a1599873b3bc3867677de5c05b02b3df39e596cbedae7`
  → **主序列是在同一份 KB 状态上测的**。
- **该指纹的存续区间（实测）**：至少从 07:33:17（CLI 序列 C 第 1 次）到 07:36:09 一直是
  `0d48111f…`；**07:36:09 被改成 `da81e1ee1bf603e8a1566ad27b812a4473a12d3342c14798da7251d890dcfab6`**。
  定位到唯一变化文件：**`kb/l6/registry/l6.json`**（`stat` mtime `07:36:09`；其余 guard 文件 mtime 均 ≤ 07:32:54，
  `kb/l4/canonical/` 5 个文件 mtime 全为 09-30）。
  即：**指纹变化发生在全部计时序列跑完之后**（CLI 07:33:17–28、API 07:33:34–47 与 07:34:06–25），
  不影响上面任何一组时延数字的 KB 一致性。
- 另一后果：三轮分段 driver 的 `BM25()` 从 860 ms 摆到 1341 ms，**机器同时在跑别人的写库任务**，
  所以时延绝对值偏保守（偏高），不是偏低。

---

## 7. 本次测量在库里留下的文件（工具自己写的，不是我改的）

**我没有编辑任何已有文件**；下面这些是**被测工具自身的审计行为**产生的（读数时刻 **07:37:10**，
之后仍在增长，因为平行会话还在写）：

| 产物 | 数量 | 谁的机制 |
|---|---|---|
| `kb/l7/reports/<run_id>.review.md` + `.md` + `.json` | **28 组 × 3 = 84 个**（新文件合计 86 个，另 2 个 .md 非三件套） | 每次 `POST /review`（`kb_api.py:249` `write_report=True`）各写 3 份；已核对我保存的 **15 份响应，15/15 三件套齐全** |
| `kb/l7/runs/<run_id>.json` + `index.jsonl` 追加行 | 索引 293 → 360 行（+67）；`runs/*.json` 286 → 340 个 | `with_kb_evidence.py:184-195` 的 `run_record`，每次 `run()` 都写；**+67 不全是我的**，见 §6 |
| `kb/l7/reports/batch12-C-…md` / `batch12-D-block-agent-path-20261002.md` | 2 | **不是我的**（平行会话） |

- CLI 路径**不写报告**（§5.5 的 `--dry-run` 恒真），但**仍写 run 记录**。
- **没有**改动 `decide()` / `kb_pipeline.py` / `kb/l4/canonical/` 下的任何内容（结构与指纹见 §6）。

---

## 8. 失败与报错（逐字）

**没有步骤失败**：CLI 6+6+8 次全部 `rc=0`；API 6+8+9 次全部 `http_code=200`；
guard 校验的 16 次运行全部 before==after（无一次 DROP）。

测量过程中只出现两条**非致命 Python 警告**（在 §5.4 的"向量路额外成本"单独实测时，逐字）：

```
/Users/lute/Library/Python/3.9/lib/python/site-packages/urllib3/__init__.py:35: NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with 'LibreSSL 2.8.3'. See: https://github.com/urllib3/urllib3/issues/3020
  warnings.warn(
/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l6/retriever.py:308: UserWarning: The model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 now uses mean pooling instead of CLS embedding. In order to preserve the previous behaviour, consider either pinning fastembed version to 0.5.1 or using `add_custom_model` functionality.
  self.model = TextEmbedding(model_name=self.meta["model"], **kw)
```

其余值得记的环境事实：解释器为 `/usr/bin/python3`（`sys.executable` 实测
`/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/...`，Python 3.9.6），
`uvicorn 0.39.0 / fastapi 0.128.8`。

---

## 9. 方法与边界（可复现）

**插桩技术（未改动任何被测文件）**：`/tmp` 下的 driver 脚本用 `importlib.util.spec_from_file_location`
按路径加载真实模块，再用**包装真实函数**（`perf_counter` 前后夹）计时；`layer_units` 内部的
`exec_module` / `BM25()` 通过替换 `importlib.util.spec_from_file_location` 为**loader 代理** +
计时子类来测（**不是**改源码、也不是猜函数名——所有名字都先从
`with_kb_evidence.py`、`review.py:548-720`、`retriever.py:251-341` 读出来）。

driver 清单：`/tmp/kb12/drv_cli_segments.py`（适配器段）、`/tmp/kb12/drv_sub_segments.py`（review.py 段）、
`/tmp/kb12/drv_units_segments.py`（BM25 段）、`/tmp/kb12/drv_warm_and_reports.py`（同进程重复调用 + 报告写盘）、
`/tmp/kb12/drv_vector_cost.py`（向量路额外成本）、`/tmp/kb12/run_cli_guarded.sh`、`/tmp/kb12/run_api_cold_warm.sh`。

**边界（别把这张表读成超出它的东西）**：

1. 测的是**确定性内核**：CLI 适配器与 HTTP API。**不含 agent 的推理/编排时间**。
   若 DoD 的「40–60 s」指的是"用户说一句话到拿到报告"的**端到端含模型**时延，那 40–60 s 里
   绝大部分预算根本不是花在这里——本次测的是它的**下界的地板**。
2. 单机、单输入、单次会话；n=8，**不构成统计结论**，只报 P50 与 MAX。
3. 机器同时有第三方写库任务在跑（§6），绝对值偏保守。
4. 未测：并发请求、冷文件系统缓存（首次上电）、其他输入文本、其他 `--channel/--product-line`。
