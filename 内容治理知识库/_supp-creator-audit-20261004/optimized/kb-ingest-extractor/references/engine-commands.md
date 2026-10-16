# kb-ingest-extractor · 引擎命令行与两个查询档

> 本文件由 SKILL.md §2 / §2.1 下沉而来（信息**逐字保留**，正文只留引擎名、两态与缺口口径）。
> 要敲命令、要对查询档口径时读本文件。

## 一、两个层主引擎

```bash
# L1：把新资源抽成单元（写 kb/l1/**）
kb/kbpy l8/extract_l1_new_resources.py <RUN> [--apply]

# L2：切分（**本仓库唯一「不带 --apply 即预演」的层主引擎**）
kb/kbpy l8/l2_split_run.py <RUN>              # 预演：只打印将追加多少行
kb/kbpy l8/l2_split_run.py <RUN> --apply      # 落盘：追加 units / index / manifest
```

## 二、两个只读查询档

想「查一下 L1/L2 现在什么水位」时**没有写档可调就走查询档**；查出问题再走写档，别直接开 `--apply`：

```bash
kb/kbpy l7/scripts/l1_status.py [--json]     # L1 台账分桶：已产出正文 / 待处理 / 不适用 / 已失效
kb/kbpy l7/scripts/l2_status.py [--json]     # L2 台账 result + 单元行数 + 最新陈旧度审计
```

**只读**：只读 `kb/l1/manifest_l1.jsonl`、`kb/l2/manifest_l2.jsonl`、`kb/l2/units.jsonl`、
已有的 `kb/l2/runs/*-staleness.json`。**不写任何文件、不落报告、不跑审计。**

两条口径，别当成缺陷去"修"：

1. **陈旧度判据在 `kb/l8/l2_staleness_audit.py`，本查询档不重写它**（同一判据写两处，第二处必然过期）。
   但那个脚本**会写** `kb/l2/runs/<RUN>-staleness.json`，**所以它不能当查询档用**；
   `l2_status.py` 因此只读它的**最新报告**。
2. **那份报告不记输入哈希/水位** → 无法自证是否仍代表当前数据。`l2_status.py` 用
   「报告 mtime vs 输入 mtime」给**弱判据**并标 `inputs_unverifiable=true`。
   **弱判据只用于提示，不当结论。**
