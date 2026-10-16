#!/usr/bin/env python3
"""W 批（W019 / W023 / W036）：把生成器产出的 509 条与 4 个元文件落进 kb/view。

⚠ 本脚本**不自己写任何被 node 读取的文件**，一律走 shell `cp`。

为什么（2026-09-29 实测，代价是一轮 509 条 E001 全红 + 基线被刷成 0 条）：
这台机器上有一层「写封装」：同一份 4,532 字节的 md，
  · `cp` 落盘 → node 读到 4,532 字节，首 3 字节 `---`  ✅
  · `shutil.copy2` 落盘 → node 读到 8,628 字节，首字节是随机二进制 ❌
    8,628 = 4,532 + **4,096** —— 即「4096 字节前缀 + 原文」的信封。
而 **Python 的 stat / sha256 / head 对信封完全免疫**：它照样报 4,532 字节、
sha256 与源文件一致。所以上一版脚本里的「明文自检」（用 Python 读首 3 字节）
**结构上就不可能发现这个缺陷** —— 它给了我一个假绿灯，然后加载器报 509 条 E001「缺 frontmatter」。

结论（写通道纪律）：
  1. 落进 `kb/view` 的文件只用 shell `cp`（或 node）写；**不要用 Python 写**。
  2. 校验必须用**消费方运行时**（node / 加载器），不要用自己的语言自证。
  3. `cp` 前先留底，且留底也要用 `cp`（否则留底本身是信封，回滚会把信封带回来）。

生成器管理的 `_meta` 文件一共 4 个（读代码确认）：
  collections.yaml / kb-classes.yaml / workbench-mirror.json / derivation.json
其余 `_meta/*` 与 `3_措辞表达库/tests/` 下的文件不是生成器产物，必须原样保留。

`evidence_group` 在加载器 GOVERNANCE_FIELDS 内（参与检索排序），故本次回填是**治理事件**:
先在 ledger.ndjson 补 why，再刷新条目基线，否则 509 条会一起报 W034。
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys

KB = "kb"
VIEW = f"{KB}/view"
STAGE = f"{KB}/l8/_stage/view_W"
ARCHIVE = f"{KB}/l8/_archive/fix-20260929-094703"
RUN = "20260929-1200"
COLL = "3_措辞表达库"
GEN_META = ["collections.yaml", "kb-classes.yaml", "workbench-mirror.json", "derivation.json"]
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"


def cp(src, dst):
    """唯一的落盘通道：shell cp。别换成 shutil / open()。"""
    subprocess.run(["cp", src, dst], check=True)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def node_scan(paths):
    """用 node（消费方运行时）看首字节 —— 只有它能看见信封。"""
    script = f"{KB}/.work/which_enveloped.mjs"
    r = subprocess.run(["env", "ELECTRON_RUN_AS_NODE=1", DSH, script, *paths],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main():
    if not os.path.isdir(STAGE):
        raise SystemExit(f"staging 不存在：{STAGE}")
    stage_md = sorted(glob.glob(f"{STAGE}/{COLL}/L1-facts/*.md"))
    live_md = sorted(glob.glob(f"{VIEW}/{COLL}/L1-facts/*.md"))
    if len(stage_md) != 509 or len(live_md) != 509:
        raise SystemExit(f"条目数不对：staging {len(stage_md)} / 现网 {len(live_md)}")

    # ── 留底（用 cp，且清掉旧的信封版留底）────────────────────
    bak = f"{ARCHIVE}/view_before_W"
    if os.path.isdir(bak):
        shutil.rmtree(bak)
    os.makedirs(f"{bak}/L1-facts")
    for p in live_md:
        cp(p, f"{bak}/L1-facts/{os.path.basename(p)}")
    for f in GEN_META:
        if os.path.exists(f"{VIEW}/_meta/{f}"):
            cp(f"{VIEW}/_meta/{f}", f"{bak}/{f}")

    # 留底本身也要用 node 验：信封版的留底在回滚时会把信封带回来
    probe = node_scan([f"{bak}/L1-facts/{os.path.basename(live_md[0])}"])
    head_ok = probe[0]["head"].startswith('"---')
    print(f"留底：{len(live_md)} md + {len(GEN_META)} 元文件（node 验首字节 {'明文 ✓' if head_ok else '信封 ✗'}）")
    if not head_ok:
        raise SystemExit("留底被写成信封，停止 —— 否则回滚会失败")

    # ── 落盘：509 条 md（cp）──────────────────────────────────
    changed = 0
    for src in stage_md:
        dst = f"{VIEW}/{COLL}/L1-facts/{os.path.basename(src)}"
        if not os.path.exists(dst) or sha(src) != sha(dst):
            cp(src, dst)
            changed += 1
    print(f"落盘 md：{len(stage_md)} 条中 {changed} 条有变化（cp 通道）")

    # ── 落盘：4 个生成器管理的元文件（cp）────────────────────
    for f in GEN_META:
        src, dst = f"{STAGE}/_meta/{f}", f"{VIEW}/_meta/{f}"
        tag = "变化" if (not os.path.exists(dst) or sha(src) != sha(dst)) else "未变"
        cp(src, dst)
        print(f"  _meta/{f:24} {tag}")

    # ── 账本补 why（幂等：同 run_id+action+fields 已存在则跳过）──
    led = f"{VIEW}/_meta/ledger.ndjson"
    existing = []
    if os.path.exists(led):
        for line in open(led, encoding="utf-8"):
            if line.strip():
                try:
                    existing.append(json.loads(line))
                except Exception:
                    pass
    dup = [r for r in existing if r.get("run_id") == RUN
           and r.get("action") == "governance_backfill" and r.get("fields") == ["evidence_group"]]
    if dup:
        print(f"账本：已有同批记录 1 行（{len(dup[0].get('targets') or [])} 个 targets），跳过")
    else:
        ids = sorted(os.path.basename(p)[:-3] for p in stage_md)
        row = {
            "action": "governance_backfill",
            "targets": ids,
            "human": False,
            "actor": "agent (kb/.work/fix_w_batch.py)",
            "authorized_by": "用户批准批次：F11 → W023/W036/W019/W035/W025 + E026 登记",
            "run_id": RUN,
            "fields": ["evidence_group"],
            "why": (
                "回填 evidence_group=rule（509 条全部为 rules.jsonl 蒸馏出的可判定规则，"
                "kind=fact、L1-facts、每条带 p_level + 命中表达 + 处理方式）。"
                "该字段在加载器 GOVERNANCE_FIELDS 内、参与检索排序，故属治理事件而非排版调整："
                "按 W034 的要求在此留 why，然后刷新条目基线。"
                "本行 human=false —— 本次是 agent 按人工批准的批次执行，**不冒充人工先例**。"
            ),
        }
        # 追加用 shell，避免 Python 写封装
        subprocess.run(["bash", "-c", f"cat >> {led}"], input=json.dumps(row, ensure_ascii=False) + "\n",
                       text=True, check=True)
        print(f"账本：追加 1 行（targets {len(ids)} 条）")

    # ── 自检：**用 node**，不要用 Python ──────────────────────
    probe = node_scan([f"{VIEW}/{COLL}/L1-facts/{os.path.basename(p)}" for p in stage_md[:3]])
    bad = [x for x in probe if not x["head"].startswith('"---')]
    print(f"node 验首字节（抽 3 条）：异常 {len(bad)} 个")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
