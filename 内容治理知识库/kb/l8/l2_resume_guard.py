#!/usr/bin/env python3
"""L2 补切续跑闸门（2026-09-30）。

解决一个问题：**上一轮补切中途被打断，怎么保证续跑不会把已切过的行再追加一遍。**

结论先说：`l8/l2_split_run.py` 的缺口判据是「该资源有没有**当前正文 sha** 的单元」
（第 57–59 行 `_cur_sha` + `gap`），**每轮从 units.jsonl 现算**，不存游标、不存偏移量，
写盘用的又是 `open(...,'a')` + 按 unit_id 去重（unit_id 含 source_sha256）。
所以「再把已切过的行追加一遍」在正常路径上不会发生。

**但闸门不能只靠读代码相信它，而且有三处它管不到的地方**（本脚本就是来堵这三处的）：

  ① units 写进去了、index 没跟上  —— 引擎是三个文件**顺序追加**（units → index → manifest），
     任一步之间被杀，后面的文件就永久缺口；而下一轮的 gap 只看 units，**不会补写 index**。
     本库现存 529 行就是这么来的（见 l2.json.index_projection）。
  ② manifest 没跟上 —— 残行会让 C3「账实上下界」的诚实下界 `max(unit_count)` 变小。
  ③ unit_count 口径未定（N3）—— 台账行数与实际单元数本来就对不齐，不能用行数差判健康。

用法（**默认只预演，不写盘**）：

    kb/kbpy l8/l2_resume_guard.py <RUN>              # 补切前 / 补切后各跑一次
    kb/kbpy l8/l2_resume_guard.py <RUN> --apply      # 前面挂上引擎的落盘（等价于引擎 --apply）
    kb/kbpy l8/l2_resume_guard.py --json             # 只输出机器可读快照

它做的事：
  基线快照 → 跑引擎（预演或落盘）→ 复算增量 → 逐条核对：
  G1 预演说 +N，落盘后 units 必须恰好 +N
  G2 index 增量必须等于 units 增量（不等 → ①型残行，**当场红**）
  G3 manifest 增量必须等于「新覆盖资源数」（不等 → ②型残行）
  G4 幂等收敛：落盘后再预演一次必须报 +0
  G5 无重复 unit_id、无内容级重复行（res,sha,splitter,type,anchor,order）

---- 反测（证明闸门真的会红，不碰真库）--------------------------------------
本闸门 2026-09-30 在临时夹具上反测过，未改动真库一个字节：

  · 夹具：复制 1 个 l1 子库 + 少量 units/index/manifest，扰动一个 artifact 的
    `source_sha256` 造出真缺口 → 预演报「将追加 520 行」，**只读不写**（已复核）。
  · 正路 --apply：G1/G2/G3/G4/G5 全绿，units +520 == 预演 +520、再预演 +0。
  · 打断反测：用假引擎让 `units.jsonl` 追加成功、`index` 那一步被丢弃 →
    **G2 立即红**（index +0 != units +12），而 **G4 仍然报 +0 收敛** ——
    这恰好证明①型残行不会被下一轮补写，只能靠本闸门当场抓。

反测入口：`KB_L2_GUARD_ROOT=<夹具目录> kb/kbpy l8/l2_resume_guard.py <RUN>`。
"""
import collections
import hashlib
import json
import os
import subprocess
import sys
import time

# REPO = 仓库根（含 kb/ 的那一层）。默认按 cwd 走；反测时用 KB_L2_GUARD_ROOT 指向夹具目录，
# 好在「不碰真库」的前提下把闸门弄红、确认它真的会红（与 l2_gate.py 的 KB_GATE_KB 同一套路）。
REPO = os.environ.get("KB_L2_GUARD_ROOT") or (
    os.getcwd() if os.path.isdir("kb/l2")
    else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROOT = f"{REPO}/kb"
L1, L2 = f"{ROOT}/l1", f"{ROOT}/l2"
ENGINE = f"{ROOT}/l8/l2_split_run.py"
KBPY = f"{ROOT}/kbpy"

APPLY = "--apply" in sys.argv
JSON_ONLY = "--json" in sys.argv
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
RUN = _args[0] if _args else time.strftime("%Y%m%d-%H%M")
if APPLY and RUN not in [a for a in sys.argv[1:] if not a.startswith("--")]:
    # 落盘必须有具名 run：否则 run_id 会退化成时间戳，provenance 归因不稳
    RUN = RUN + "-resume"


def rows(path):
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as fh:
        return sum(1 for l in fh if l.strip())


def snapshot():
    return {
        "units": rows(f"{L2}/units.jsonl"),
        "index": rows(f"{L2}/index/l2.jsonl"),
        "manifest": rows(f"{L2}/manifest_l2.jsonl"),
        "units_bytes": os.path.getsize(f"{L2}/units.jsonl"),
        "index_bytes": os.path.getsize(f"{L2}/index/l2.jsonl"),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def load_units():
    with open(f"{L2}/units.jsonl", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def run_engine(apply_):
    cmd = [KBPY, "l8/l2_split_run.py", RUN] + (["--apply"] if apply_ else [])
    # 引擎内部把 kb/l0、kb/l1、kb/l2 写成**相对 cwd** 的路径，所以必须 cd 到含 kb/ 的那一层跑。
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def parse_dryrun(out):
    """从预演输出里取「将追加 N 行」，取不到返回 None（取不到就是红，不许猜 0）。"""
    for line in out.splitlines():
        if "将追加" in line and "units.jsonl +" in line:
            try:
                seg = line.split("units.jsonl +", 1)[1]
                return int(seg.split("行", 1)[0].strip())
            except Exception:
                return None
    return None


def ledger_sha():
    """台账指纹：把三个文件的 (行数, 字节数) 哈希一下，用来证明「没落盘」。"""
    return hashlib.sha256(json.dumps(snapshot(), sort_keys=True).encode()).hexdigest()[:16]


def dup_audit():
    U = load_units()
    ids = collections.Counter(u["unit_id"] for u in U)
    dup_id = sum(v - 1 for v in ids.values() if v > 1)
    K = lambda u: (u["resource_id"], u.get("source_sha256"), u.get("splitter_version"),
                   u.get("unit_type"), u.get("anchor"), u.get("order_in_parent"))
    dup_row = sum(v - 1 for v in collections.Counter(K(u) for u in U).values() if v > 1)
    null_sha = sum(1 for u in U if not u.get("source_sha256"))
    return {"rows": len(U), "dup_unit_id": dup_id, "dup_row": dup_row,
            "null_source_sha": null_sha, "distinct_resources": len({u["resource_id"] for u in U})}


def main():
    base = snapshot()
    if JSON_ONLY:
        print(json.dumps({"run": RUN, "baseline": base, "units_audit": dup_audit()},
                         ensure_ascii=False, indent=1))
        return 0

    print("=" * 74)
    print(f"L2 补切续跑闸门  run_id={RUN}  模式={'落盘(--apply)' if APPLY else '预演(只读)'}")
    print(f"  基线：units {base['units']} 行 / index {base['index']} 行 / manifest {base['manifest']} 行")
    print(f"  基线下游缺口：index 落后 units {base['units'] - base['index']} 行"
          f"（历史孤投影，见 l2/registry/l2.json.index_projection；本轮不去动它）")
    print("-" * 74)

    # ---- 预演（落盘模式下也要先预演，拿 N）----
    rc1, out1 = run_engine(False)
    n_planned = parse_dryrun(out1)
    print(out1.strip())
    print("-" * 74)
    if rc1 != 0:
        print(f"❌ 预演本身失败（退出码 {rc1}）——本轮不落盘。")
        return 1
    if n_planned is None:
        print("❌ 预演输出里读不到「将追加 N 行」——口径变了，人工看输出，别猜 0。")
        return 1

    red = []
    if n_planned == 0:
        print("✅ 待补切 0 行。**上一轮已经切完或已收敛**，本轮落盘无意义（也不会重复追加）。")
    else:
        print(f"预演：将追加 {n_planned} 行。")

    if not APPLY:
        print("（预演模式，未写盘。加 --apply 落盘。）")
        return 0

    if n_planned == 0:
        print("落盘模式但 N=0：直接退出，不写盘、不产生空 run 记录。")
        return 0

    # ---- 落盘 ----
    rc2, out2 = run_engine(True)
    print(out2.strip())
    if rc2 != 0:
        print(f"❌ 引擎落盘失败（退出码 {rc2}）——**先看下面 G2/G3，再决定是否重跑**。")
        red.append("引擎退出码非 0")
    after = snapshot()
    d_units = after["units"] - base["units"]
    d_index = after["index"] - base["index"]
    d_manifest = after["manifest"] - base["manifest"]

    # ---- G1 ---- 预演数与落盘数必须一致
    print("-" * 74)
    if d_units == n_planned:
        print(f"G1 ✅ units +{d_units} == 预演 +{n_planned}（不多不少；这就是「不会重复追加」的证据）")
    else:
        print(f"G1 ❌ units +{d_units} != 预演 +{n_planned}")
        red.append(f"G1 units 增量 {d_units} != 预演 {n_planned}")

    # ---- G2 ---- index 必须与 units 同步（①型残行）
    if d_index == d_units:
        print(f"G2 ✅ index +{d_index} 与 units 同步")
    else:
        print(f"G2 ❌ index +{d_index} != units +{d_units} —— **残行**：这三个文件是顺序追加的，")
        print(f"      被中断时后面的文件会缺口，而下一轮的 gap 只看 units，**永远不会补写 index**。")
        print(f"      修法：按 unit_id 把 {L2}/index/l2.jsonl 缺的行补成 units 的子集投影（只追加，不改既有行）。")
        red.append(f"G2 index 落后 units {d_units - d_index} 行")

    # ---- G3 ---- manifest 每新增一个被覆盖资源应有一行
    a = load_units()
    newly = {u["resource_id"] for u in a[int(base["units"]):]}
    if d_manifest == len(newly):
        print(f"G3 ✅ manifest +{d_manifest} == 新覆盖资源 {len(newly)} 个")
    elif d_manifest < len(newly):
        print(f"G3 ❌ manifest +{d_manifest} < 新覆盖资源 {len(newly)} 个 —— 台账缺行，"
              f"C3「账实上下界」的诚实下界会因此变小。")
        red.append(f"G3 manifest 少 {len(newly) - d_manifest} 行")
    else:
        print(f"G3 ⚠️ manifest +{d_manifest} > 新覆盖资源 {len(newly)} 个 —— 可能有重切对（invalidated→split），人看。")

    # ---- G4 ---- 幂等收敛：再预演必须 +0
    rc3, out3 = run_engine(False)
    n2 = parse_dryrun(out3)
    if n2 == 0:
        print("G4 ✅ 再预演报 +0 行 —— 幂等收敛，续跑不会重复追加。")
    else:
        print(f"G4 ❌ 再预演仍报 +{n2} 行 —— 缺口没闭合（可能是本批被 status/正文变更反复重切），要看 run 记录。")
        red.append(f"G4 未收敛，仍将追加 {n2} 行")

    # ---- G5 ---- 重复行审计（全量复算，不靠增量自证）
    d = dup_audit()
    if d["dup_unit_id"] == 0 and d["dup_row"] == 0:
        print(f"G5 ✅ 全量复算：{d['rows']} 行，重复 unit_id 0 / 内容级重复行 0")
    else:
        print(f"G5 ❌ 重复 unit_id {d['dup_unit_id']} / 内容级重复行 {d['dup_row']}")
        red.append("G5 存在重复行")
    if d["null_source_sha"]:
        print(f"     ⚠️ {d['null_source_sha']} 行的 source_sha256 为空 —— 这些资源的幂等键退化成 None，")
        print(f"        正文若重抽，gap 判据仍然判「已覆盖」，属于**静默漏切口**（不是重复追加）。")

    print("=" * 74)
    print(f"本轮台账指纹 {ledger_sha()} ｜ units {base['units']}→{after['units']} "
          f"index {base['index']}→{after['index']} manifest {base['manifest']}→{after['manifest']}")
    # 历史下游缺口有没有被本轮缩小 —— G2 只管本轮增量，**不会**替历史残行背书，
    # 所以这里必须把「历史缺口原样保留」说出来，否则容易被读成「修好了」。
    bg_before = base["units"] - base["index"]
    bg_after = after["units"] - after["index"]
    if bg_before > 0:
        print(f"⚠️ 历史下游缺口（index 落后 units）：{bg_before} → {bg_after} 行。"
              f"{'本轮未动它（与预期一致）。' if bg_after == bg_before + d_units - d_index else ''}"
              f" 这是孤投影，按 l2.json.index_projection 的既有裁决「登记，不重建」。")
    if red:
        print("结论：❌ 红 " + str(len(red)) + " 项 —— " + "；".join(red))
        return 1
    print("结论：✅ 全绿（补切可安全续跑，未产生重复行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
