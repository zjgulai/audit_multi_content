#!/usr/bin/env python3
"""每轮 L0 同步收口后跑：把这一轮的事实记下来，并生成"该改什么"的**候选**。

## 这个脚本在自成长里的位置（读 SKILL.md §8）

    §8.1 事实层（本脚本）—— 全自动、append-only、只从产物机械推导，不含判断
    §8.2 规则层            —— **不许自动改**：红线/闸门/四态口径/preflight 通过线，一律要人确认

本脚本**只写两个地方**：
    · kb/l8/retro/ledger.ndjson          运行台账（追加，一行一轮）
    · <库根>/l7/skills/kb-l0-feishu/references/gotchas.proposals.md   升级候选（人与已确认坑分开存放）
      ↑ 落点**固定在库内源**（2026-09-30 修）：不按脚本自身位置推。装载位
        `~/.dsh/skills/…` 是**只读运行副本**（`l7/registry/skills.yaml` :: `meta.single_writer_rule`）；
        历史事故正是「从装载位调用 → 写进装载位 → 源不动 → `skills_check` 第 3 类连红四次」。
        候选写完**当场镜像到装载位**（只镜这一个文件，见 `mirror_to_install_slots`）：
        四次红的形态全是"只写了一侧"，写哪一侧另一侧就旧 —— 所以由唯一的写者
        把两个副本当**一次事务**写完。镜像只在**权威库根**下发生。

它**不写** SKILL.md、不写 gotchas.md 正文、不写任何闸门 —— 因为拿证据自动改判据，
等于让被考核的一方自己改考卷。自动化的应该是"发现"，不是"裁决"。

## 它怎么推导（全部来自既有产物，不需要人填）

    RUN 产物      kb/l8/runs/<RUN>-*.json
    关键量        l0-align 的 summary（same/only_feishu/only_l0/changed/未登记）
                  非记录核验的四态计数、envelope_census 结论、scope 缺口数、索引层是否跑过
    原因码集合    从上面各报告里提取（gone / no_permission / no_scope / forbidden /
                  unreachable / drift / not_verified …）
    与上轮差      新出现的原因码、新出现的对象键（首次出现时间）
    重复计数      同一原因码 / 同一失败模式累计出现轮数 → ≥2 轮生成"升级建议"

用法：
    python3 kb/l7/skills/kb-l0-feishu/scripts/retro.py <RUN>    # 从**库内源**跑（推荐）
    python3 scripts/retro.py <RUN> --kb <库根>                   # 默认按 ~/.dsh/Momcozy知识库/kb 找
    # 候选一律落库内源；从装载位调用也不会再写装载位（已加护栏，见下）
"""
import collections
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
CANON_KB = os.path.realpath(os.path.expanduser("~/.dsh/Momcozy知识库/kb"))   # 权威库根：只有它才镜像装载位
KB = os.environ.get("L8_KB_ROOT") or os.path.expanduser("~/.dsh/Momcozy知识库/kb")
if "--kb" in sys.argv:
    KB = sys.argv[sys.argv.index("--kb") + 1]
if not RUN:
    raise SystemExit(__doc__)

# 脚本自己的位置 —— **只用来读自己的版本号**（tool_version），不再用来定落点。
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(KB, "l8", "retro", "ledger.ndjson")

# 候选的落点（2026-09-30 修）：按**库根**解析到库内源，**不再** `SKILL/references/…`。
# 为什么改：原先按"脚本自己旁边"写，而从装载位调用本脚本就写进了装载位，
# 源不动 → `skills_check` 第 3 类（副本不一致）在 13:10 / 13:38 / 13:46 / 14:50 连红四次，
# 每次都要人把装位回灌源才收口。单一写入者纪律见 `l7/registry/skills.yaml`。
SKILL_ID = "kb-l0-feishu"        # 与登记表 skills.yaml 的 id、库内源目录名一致
PROPOSALS = os.path.join(KB, "l7", "skills", SKILL_ID, "references", "gotchas.proposals.md")

# 护栏：落点绝不许命中装载位 —— 历史事故的形态就是"写进了 ~/.dsh/skills/"。
# 用 abspath+expanduser 比：`--kb` 传进来的值可能是 `~/…` 字面量，直接比会漏。
INSTALL_SLOTS = tuple(os.path.expanduser(p).rstrip("/") + os.sep
                      for p in ("~/.dsh/skills", "~/.agents/skills"))
_CAND = os.path.abspath(os.path.expanduser(PROPOSALS))
if _CAND.startswith(INSTALL_SLOTS):
    raise SystemExit("[retro] 拒绝写入装载位：%s\n"
                     "        候选只写库内源；装载位是只读运行副本"
                     "（l7/registry/skills.yaml::meta.single_writer_rule）" % _CAND)


def tool_version():
    """记下写这行账时的 skill 版本 —— 台账要能回答"这行是哪版工具写的"。"""
    try:
        for line in open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8"):
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None

# 原因码词表（与 SKILL.md §1 红线 4 / §2 四态制一致）
REASON_CODES = ["gone", "no_permission", "no_scope", "not_found",
                "blocked_by_library_setting", "forbidden", "unreachable",
                "drift", "not_verified", "empty", "invalidated", "retracted"]


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def atomic_write(path, data: bytes):
    """落盘：先写 /tmp，再用**子进程 `/bin/cp`** 覆盖目标。

    2026-09-30 实测（对照实验 + 两次真实踩坑，见 gotchas「信封态」一栏）：
    python 直接 `open(path, "w")` 新建或截断文件后，bash 侧的 `stat`/`wc -c`
    会看到「真实长度 **+4096**」的虚高尺寸 —— 内容其实是完整明文，但 harness 的
    read 工具按 stat 尺寸去读，于是判成 **binary file、读不了**。
      · python 直接建/截断                       → 信封态
      · `os.replace(tmp, path)` 改名覆盖          → 当场对得上，但**下一轮再 stat 又变信封**
      · 子进程 `/bin/cp` 覆盖到既有目标           → 明文（实测两次都稳）
    所以本脚本一律走 `mkstemp → 写 → /bin/cp`；`os.replace` 只作 cp 不可用时的退路。
    这既是自保，也是示范 —— 脚本自己产出的东西，别成为库的 envelope 闸门抓的对象。
    """
    fd, tmp = tempfile.mkstemp(dir="/tmp", prefix="retro-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    try:
        os.chmod(tmp, 0o644)
    except OSError:
        pass
    if os.path.exists(path):          # cp 覆盖既有文件：保留目标路径上的既有 inode
        try:
            if subprocess.run(["/bin/cp", tmp, path]).returncode == 0:
                os.unlink(tmp)
                return
        except OSError:
            pass
    os.replace(tmp, path)             # 退路：目标还不存在，或 cp 不可用


def append_lines(path, lines):
    """保留原有内容、只往后追加 —— 语义仍是 append-only，只是换了落盘方式。"""
    old = b""
    if os.path.exists(path):
        with open(path, "rb") as fh:
            old = fh.read()
        if old and not old.endswith(b"\n"):
            old += b"\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, old + "".join(lines).encode("utf-8"))


def mirror_to_install_slots(path):
    """把**刚写的这一个文件**镜像到装载位，让「源 == 装位」在写的那一刻就成立。

    为什么由脚本自己干（2026-09-30 第 4 次复发后补）：这个文件四次第 3 类红的形态**全都是
    "只写了一侧"** —— 写装位则源旧，写源则装位旧，两种都红。"记得收尾再 rsync 一次"已被
    四次事故证明靠不住，所以让唯一的写者把两个副本当**一次事务**写完。
    只镜像**自己刚写的这一个文件**：别的文件万一漂移，仍要留给 `skills_check` 去发现，
    不许被顺手抹平（那会把真信号洗成静默）。

    只在**权威库根**下才镜像 —— 拿沙箱 / 视图 / 派生副本跑出来的内容，不许写进真装载位。
    """
    if os.path.realpath(KB) != CANON_KB:
        print(f"  装载位未镜像：KB 不是权威库根（{KB}）", file=sys.stderr)
        return
    rel = os.path.relpath(path, os.path.join(KB, "l7", "skills", SKILL_ID))
    for slot in INSTALL_SLOTS:
        dst = os.path.join(slot, SKILL_ID, rel)
        if not os.path.exists(dst):
            continue
        try:
            if open(dst, "rb").read() == open(path, "rb").read():
                continue
        except OSError:
            pass
        # 与 append_lines 同一条写通道：子进程 /bin/cp，不落信封态
        if subprocess.run(["/bin/cp", path, dst]).returncode == 0:
            print(f"  装载位已镜像: {dst}")
        else:
            print(f"  ⚠ 装载位镜像失败：{dst} —— 不修就是一条 skills_check 第 3 类红",
                  file=sys.stderr)


rep = load(os.path.join(KB, "l8", "runs", f"{RUN}-l0-align.json"))
# 容错（2026-09-30 补）：阶段可能跑在不同 RUN 下（实测一次同步里我用了 8 个 RUN —— 违反"统一 run_id"）。
# 所以 align 报告缺失**不拒记**：记 null 并生成一条候选，别让"记账"本身成为需要完美执行的动作。
ALIGN_RUN = RUN
if rep is None and "--align-run" in sys.argv:
    ALIGN_RUN = sys.argv[sys.argv.index("--align-run") + 1]
    rep = load(os.path.join(KB, "l8", "runs", f"{ALIGN_RUN}-l0-align.json"))

summary = (rep or {}).get("summary") or {}
man = (rep or {}).get("manifest") or {}
entry = {"run": RUN, "align_run": ALIGN_RUN if rep else None,
         "at": time.strftime("%Y-%m-%d %H:%M:%S"),
         "retro_version": tool_version(),
         "record_layer": {k: summary.get(k) for k in ("same", "only_feishu", "only_l0", "changed", "pull_failed")}
                         if rep else None,
         "unregistered_record_files": man.get("record_files_not_registered_total"),
         "reason_codes": {}, "stage_products": {}, "proposals": []}

# 阶段产物的识别：**按关键词从实际文件发现**，不写死文件名。
# 2026-09-30 教训：第一版把名字写死，其中三个与真实文件名不符
# （真实是 `-l0-nonrecord-verify.json` / `-l0-nonrecord-verify2.json`，L6 的 scope-append 还在 kb/l6/runs/），
# 于是它每轮都把已跑的阶段误报成"缺失" —— 正是 gotchas 里"脚本读死路径"那一类毛病。
STAGE_PATTERNS = [("nonrecord-verify2", "nonrecord2"), ("nonrecord-verify", "nonrecord"),
                  ("l0-schema-align", "schema"), ("l0-align", "align"),
                  ("close-scope-gaps", "scope_gaps"), ("video-filter", "video"),
                  ("url-content-verdict", "shingles"), ("url-verify", "urls"),
                  ("l0-ingest", "l0_ingest"), ("scope-append", "l6_scope")]
found = {}
for d in ("l8", "l6"):
    for p in sorted(glob.glob(os.path.join(KB, d, "runs", f"{RUN}-*.json"))):
        found.setdefault(os.path.basename(p), []).append(os.path.relpath(p, KB))
for fname, paths in found.items():
    for kw, key in STAGE_PATTERNS:
        if kw in fname:
            entry["stage_products"].setdefault(key, paths[0])
entry["products_found"] = sorted(found)
entry["products_found_paths"] = {k: v[0] for k, v in sorted(found.items())}
if rep is not None and "align" not in entry["stage_products"]:
    # 允许 --align-run 指到别的 RUN：对齐报告确实读到了就不算缺跑
    entry["stage_products"]["align"] = f"l8/runs/{ALIGN_RUN}-l0-align.json"

# 原因码：从各报告的可疑键里机械提取（不判断对错，只计数）
for p in glob.glob(os.path.join(KB, "l8", "runs", f"{RUN}-*.json")):
    try:
        blob = json.dumps(json.load(open(p, encoding="utf-8")), ensure_ascii=False)
    except Exception:
        continue
    for rc in REASON_CODES:
        n = blob.count(f'"{rc}"')
        if n:
            entry["reason_codes"][rc] = entry["reason_codes"].get(rc, 0) + n

# ---- 与上一轮做差：新出现的原因码 / 累计轮数 ----
# correction 行是"更正说明"，不是一轮运行：不计轮数、不参与原因码累计（否则会虚增轮次）。
hist = []
if os.path.exists(LEDGER):
    for line in open(LEDGER, encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            if not row.get("correction"):
                hist.append(row)
prev = hist[-1] if hist else None
seen_before = collections.Counter()
for h in hist:
    for rc in (h.get("reason_codes") or {}):
        seen_before[rc] += 1

new_codes = sorted(rc for rc in entry["reason_codes"] if seen_before[rc] == 0)
repeat = sorted((rc, seen_before[rc] + 1) for rc in entry["reason_codes"] if seen_before[rc] >= 1)
entry["new_reason_codes"] = new_codes
entry["repeat_reason_codes"] = [{"code": c, "rounds": n} for c, n in repeat]

# 阶段缺跑（"以为跑了其实没跑"是最贵的一类）。
# 但"本 RUN 找不到"≠"没跑"：一次同步里很容易跨多个 RUN 落盘（实测我用过 8 个）。
# 所以对每个缺的键，再去全量 runs 里找同名关键词的**最近一份**：
#   找到 → 归入 stages_elsewhere（性质是"run_id 口径不统一"，属流程账，不是漏跑）
#   没找到 → 才归入 stages_missing（性质是"以为跑了其实没跑"，属实质风险）
missing, elsewhere = [], {}
for kw, key in STAGE_PATTERNS:
    if key in entry["stage_products"]:      # 本 RUN 已找到，不算缺
        continue
    latest = None
    for d in ("l8", "l6"):
        for p in glob.glob(os.path.join(KB, d, "runs", f"*-{kw}.json")):
            if os.path.basename(p).startswith(RUN + "-"):
                continue
            if latest is None or os.path.getmtime(p) > os.path.getmtime(latest):
                latest = p
    if latest:
        elsewhere[key] = os.path.relpath(latest, KB)
    else:
        missing.append(key)
entry["stages_missing"] = missing
entry["stages_elsewhere"] = elsewhere

append_lines(LEDGER, [json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"])

print(f"[retro] RUN={RUN}")
print(f"  记录层: {entry['record_layer']}｜未登记 {entry['unregistered_record_files']}")
print(f"  本轮原因码: {entry['reason_codes']}")
print(f"  新出现: {new_codes or '无'}")
print(f"  累计 ≥2 轮: {entry['repeat_reason_codes'] or '无'}")
print(f"  未跑的阶段产物: {missing or '无'}")
if elsewhere:
    print(f"  落在别的 RUN 下（run_id 口径不统一，非漏跑）: {elsewhere}")
print(f"  台账: {LEDGER}（累计 {len(hist) + 1} 轮）")

# ---- 生成升级候选（只写候选区，不动已确认区）----
cands = []
for rc in new_codes:
    cands.append({"kind": "new_reason_code", "code": rc,
                  "suggest": "首次出现的原因码：确认是数据状态还是工具缺陷；若属工具缺陷，"
                             "按 §7 记入 gotchas 的『脚本自身缺陷』一栏，不要报成数据缺陷"})
for x in entry["repeat_reason_codes"]:
    cands.append({"kind": "repeat>=2", "code": x["code"], "rounds": x["rounds"],
                  "suggest": "同一原因码累计 ≥2 轮：按 gotchas §四 维护闭环，考虑升为 SKILL.md 红线"
                             "或阶段内硬规则"})
for k in missing:
    cands.append({"kind": "stage_not_run", "stage": k,
                  "suggest": "该阶段产物在本 RUN 缺失：确认是『有意跳过』还是『以为跑了』——"
                             "后者是最贵的一类失误（如 l6_build 不带 --apply 只打 [dry-run] 就退出）"})
if elsewhere:
    cands.append({"kind": "run_id_split", "stage": f"{len(elsewhere)} 个阶段落在别的 RUN 下",
                  "detail": elsewhere,
                  "suggest": "一次同步应统一一个 run_id（SKILL.md §7）：产物散在多个 RUN 下时，"
                             "retro/审计只能靠关键词回捞，容易被读成『漏跑』。不改判据，改执行习惯"})

out = [f"\n## {RUN}（{entry['at']} · retro {entry['retro_version'] or '?'}）\n\n"]
if not cands:
    out.append("- 无候选（本轮没有新原因码、没有重复项、阶段产物齐全）\n")
for c in cands:
    out.append(f"- **{c['kind']}** `{c.get('code') or c.get('stage')}`：{c['suggest']}\n")
out.append("\n> 候选由 `scripts/retro.py` 机械生成；**升为红线/改闸门必须人工确认**（SKILL.md §8.2）。\n")
if os.path.isdir(os.path.dirname(PROPOSALS)):
    append_lines(PROPOSALS, out)
    print(f"  候选已追加: {PROPOSALS}（库内源；装载位只读）")
    mirror_to_install_slots(PROPOSALS)
else:
    print(f"  ⚠ 候选未写：库内源目录不存在 → {os.path.dirname(PROPOSALS)}", file=sys.stderr)
    print(f"    本轮台账已记：{LEDGER}", file=sys.stderr)
    print("    **不要**退回「写脚本旁边」—— 那正是 2026-09-30 四次副本漂移的根因",
          file=sys.stderr)
