#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_growth.py —— 知识库 skill 的**自生长回路**。

    python3 kb/l8/skill_growth.py                 # 预演（一个字节都不落盘）
    python3 kb/l8/skill_growth.py --apply         # 真写
    python3 kb/l8/skill_growth.py --selftest      # 判据自证（离线）
    python3 kb/l8/skill_growth.py --rounds        # 只读：看历轮生长台账

## 它长的是什么，不碰的是什么（这条决定了它安不安全）

| 对象 | 会不会被自动改 | 为什么 |
|---|---|---|
| `SKILL.md` 的 **frontmatter / 触发词 / 正文** | **永不** | 改了就是改路由与行为 —— 那是「影响现有工作流」 |
| `SKILL.md` 末尾那个**已批过的指针节** | **永不**（只在人工部署时写一次） | 它由人过一次；之后由本脚本**只读校验它还在** |
| `references/会话蒸馏回灌.md` | ✅ **只追加** | 按需读，不改指令；去重靠 `case_id` |
| `references/自生长台账.md` | ✅ **只追加** | 每轮一行，写清长了什么、回验过没过、闸门结果 |

也就是说：**长的是「这个 skill 知道的事」，不是「它被要求怎么做」。**
这条是刻意的 —— 用户的要求是「优化 skill 但不要影响现有工作流」，
而「不改指令、只涨知识」是唯一能同时满足两句的做法。

## 一轮做什么（七步，任一步失败即回滚）

    ① 读候选包（会话蒸馏的产物）→ ② 逐条**回验指针**（case_id 在表里 + 引文逐字存在）
    → ③ 政策过滤（哪些 skill 可长、单轮上限）→ ④ 去重（已长过的 card_id 不再长）
    → ⑤ 备份 → ⑥ 追加 references → ⑦ 同步装载位 + 跑 `skills_check.py`
    ⇒ 第 3 类「副本不一致」不为 0 就**整个回滚**，并把它记成红

★ 单一写者纪律（`kb/l7/registry/skills.yaml` 的 `single_writer_rule`）：
  唯一可写位置是**源目录**；装载位是只读运行副本，一律由 `cp -p` 从源同步过去。
  本脚本**不直接写装载位**。

退出码：0=全过 ｜ 1=有红（已回滚）｜ 2=未测（候选包或政策读不到）｜ 3=被政策拒（超上限）
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# ★ 两层 dirname：HERE = …/内容治理/kb/l8 ⇒ ROOT = …/内容治理（**含 kb/ 的那一层**）。
#   第一版只 dirname 了一层，于是政策路径拼成 `…/kb/kb/l7/registry/…`，
#   引擎一跑就报「政策文件不存在」—— 而它看起来像个「文件没装」的问题，不是路径 bug。
#   口径抄 `kb/l8/workflow_impact_gate.py:34`。
ROOT = os.path.dirname(os.path.dirname(HERE))
POLICY = os.path.join(ROOT, "kb/l7/registry/skill-growth.yaml")
SLOT = os.path.expanduser("~/.dsh/skills")
SKILLS_CHECK = os.path.join(ROOT, "kb/l7/scripts/skills_check.py")
REF_NAME = "会话蒸馏回灌.md"
LEDGER_NAME = "自生长台账.md"
# SKILL.md 里那一节的标题 —— **只读校验它还在**，不改它
POINTER_TITLE = "会话蒸馏回灌"

CANDIDATE_GLOBS = [
    os.path.expanduser("~/project/audit_multi_content/PMO"),
    os.path.expanduser("~/Documents/skill-test/执行skills/执行skills/skills-回归测试/PMO"),
]


def today():
    return datetime.date.today().strftime("%Y-%m-%d")


# ── 政策 ────────────────────────────────────────────────────────────
def load_policy():
    if not os.path.exists(POLICY):
        return None, "政策文件不存在：%s" % POLICY
    try:
        import yaml
        d = yaml.safe_load(open(POLICY, encoding="utf-8"))
    except Exception as e:
        return None, "政策解析失败：%s" % e
    if not isinstance(d, dict) or "skills" not in d:
        return None, "政策里没有 skills 段"
    return d, None


# ── 候选包 ──────────────────────────────────────────────────────────
def find_candidate_dirs():
    """找所有 `PMO/会话蒸馏-*` 目录，按名字（含日期）倒序。"""
    out = []
    for base in CANDIDATE_GLOBS:
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if name.startswith("会话蒸馏-") and os.path.isdir(p):
                out.append(p)
    return sorted(out, reverse=True)


def read_ndjson(path):
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def load_candidates(pkg):
    """返回 (cases, judged, cards, err)。缺任何一份都算未测。"""
    cases = read_ndjson(os.path.join(pkg, "案例-v1.ndjson"))
    judged = read_ndjson(os.path.join(pkg, "正误判定-v1.ndjson"))
    cardsp = os.path.join(pkg, "schema", "Schema卡片-v1.json")
    cards = None
    if os.path.exists(cardsp):
        try:
            cards = json.load(open(cardsp, encoding="utf-8")).get("cards")
        except Exception as e:
            return None, None, None, "卡片解析失败：%s" % e
    if cases is None or judged is None or cards is None:
        return None, None, None, "候选包不完整（案例/判定/卡片 缺一）"
    return cases, judged, cards, None


def verify_card(card, cases, judged):
    """★ 自生长的**唯一硬闸门**：每条指针都必须能回源，且引文**逐字**存在。

    与生成侧（`s5_schema.py`）同一口径 —— 但这里**独立复算**，不信生成侧的自报。
    """
    ok = bad = 0
    reasons = []
    for item in card.get("条目", []):
        for p in item.get("依据", []):
            cid = p.get("case_id")
            c = cases.get(cid)
            j = judged.get(cid)
            if c is None or j is None:
                bad += 1
                reasons.append("%s：case_id 不在候选包里" % cid)
                continue
            if j.get("判定") == "待人工复核":
                bad += 1
                reasons.append("%s：拿『待人工复核』当依据" % cid)
                continue
            q = (p.get("quote") or "").strip()
            hay = (c.get("ask") or "") + "\n" + (c.get("next_human") or "")
            if not q or q not in hay:
                bad += 1
                reasons.append("%s：引文不在原文里" % cid)
                continue
            ok += 1
    return ok, bad, reasons


# ── 追加（只追加，不改已有行）────────────────────────────────────────
def read_text(p):
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def write_text(p, s):
    """写正文。**走 cp 通道**（python 直写 .md 在本机会落成 +4096 信封，读它的人打不开）。

    配方来自 `kb/l7/registry/layers.yaml` 的 `envelope_note`：
    「python 生成内容 → 写到**无扩展名**临时件 → cp 落到目标」。
    """
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp-nosuffix"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(s)
    subprocess.run(["/bin/cp", tmp, p], check=True)
    os.unlink(tmp)
    return os.path.getsize(p)


def append_block(path, header, body, marker):
    """向 `path` **追加**一段（带 marker 去重）。marker 已存在则不动。"""
    cur = read_text(path)
    if marker in cur:
        return cur, False
    sep = "" if (not cur or cur.endswith("\n\n")) else ("\n" if cur.endswith("\n") else "\n\n")
    new = cur + sep + header + "\n\n" + body.rstrip("\n") + "\n"
    write_text(path, new)
    return new, True


def append_ledger(path, line):
    cur = read_text(path)
    if not cur:
        cur = ("# 自生长台账\n\n"
               "> 由 `kb/l8/skill_growth.py` 自动追加。**这是唯一由机器写入的文件之一** ——\n"
               "> 它只记「哪一轮长了什么、回验过没过、闸门结果」，不改任何指令。\n\n"
               "| 日期 | 轮 | 新卡片 | 指针回验过 | 指针不过 | skills_check 第3类 | 结果 |\n"
               "|---|---|---|---|---|---|---|\n")
    write_text(path, cur + line + "\n")


# ── skills_check ────────────────────────────────────────────────────
RE_SUMMARY = re.compile(r"五类问题：1=(\d+)\s+2=(\d+)\s+3=(\d+)\s+4=(\d+)\s+5=(\d+)")


def _parse_summary(text):
    """从 skills_check 的**人类可读输出**里解析汇总行；解析不到返回 None（=未测）。"""
    m = RE_SUMMARY.search(text or "")
    if not m:
        return None
    return {"1": int(m.group(1)), "2": int(m.group(2)), "3": int(m.group(3)),
            "4": int(m.group(4)), "5": int(m.group(5)),
            "结论全过": ("结论：全过" in (text or ""))}


def run_skills_check():
    """跑 skills_check 并解析它**真实的**汇总行。

    ★ 第一版调的是 `[SKILLS_CHECK, "--json"]` —— **那个脚本不支持 `--json`**
      （忽略该参数、照打人类可读文本）。于是 `json.loads()` 抛异常 → 判成「未测」
      → 引擎按自己的规矩**回滚并返回 1** ⇒ **每晚静默失败、一个字节都不长**。
      更坏的是：它「看起来在正常工作」—— 作业在册、err.log 有行、没人看。
      判据改成解析它**真的会打**的那一行；**解析不到 = 未测，绝不是通过**。
      （同形状的错：部署脚本里也照抄过 `--json`，那次是我自己发现的。）
    """
    r = subprocess.run([sys.executable, SKILLS_CHECK], capture_output=True, text=True)
    counts = _parse_summary(r.stdout)
    if counts is None:
        return None, "解析不到汇总行（rc=%d）—— **未测，不是通过**" % r.returncode
    return counts, None


def class3_count(groups):
    if groups is None:
        return None
    for k in ("3", 3, "3. 副本不一致"):
        if k in groups:
            v = groups[k]
            return len(v) if isinstance(v, (list, tuple)) else int(v)
    return None


# ── 同步（唯一写者是源目录；装载位由 cp -p 同步）─────────────────────
def sync_to_slot(src_dir, slot_dir, files):
    """★ 不直接写装载位 —— 从**源**逐文件 `cp -p` 过去（single_writer_rule）。"""
    os.makedirs(slot_dir, exist_ok=True)
    for rel in files:
        s = os.path.join(src_dir, rel)
        t = os.path.join(slot_dir, rel)
        if not os.path.exists(s):
            continue
        os.makedirs(os.path.dirname(t), exist_ok=True)
        subprocess.run(["/bin/cp", "-p", s, t], check=True)


# ── 一轮 ────────────────────────────────────────────────────────────
def grow(pkg, policy, apply):
    cases_l, judged_l, cards, err = load_candidates(pkg)
    if err:
        print("✗ 未测：%s" % err)
        return 2
    cases = {c["case_id"]: c for c in cases_l}
    judged = {j["case_id"]: j for j in judged_l}
    allow = policy["skills"]
    cap = int(policy.get("max_cards_per_round", 20))
    stamp = today()
    round_id = datetime.datetime.now().strftime("%Y%m%d-%H%M")

    print("── skill 自生长 " + ("（--apply 真写）" if apply else "（预演，不落盘）"))
    print("   候选包    %s" % pkg)
    print("   卡片      %d 张" % len(cards))
    print("   政策放行  %d 个 skill" % len(allow))

    planned = []
    for card in cards:
        skill = card.get("目标skill")
        if skill not in allow:
            continue
        ok, bad, reasons = verify_card(card, cases, judged)
        planned.append((skill, card, ok, bad, reasons))

    by_skill = {}
    for skill, card, ok, bad, reasons in planned:
        by_skill.setdefault(skill, []).append((card, ok, bad, reasons))

    total_ok = total_bad = 0
    rows = []
    for skill, items in sorted(by_skill.items()):
        cfg = allow[skill]
        src = cfg["source"]
        if not os.path.isdir(src):
            print("   %-14s ⚠ 源目录不存在，跳过：%s" % (skill, src))
            continue
        ref = os.path.join(src, "references", REF_NAME)
        have = read_text(ref)
        new_items = [x for x in items if x[0]["id"] not in have]
        new_items = new_items[:cap]
        ok = sum(x[1] for x in new_items)
        bad = sum(x[2] for x in new_items)
        total_ok += ok
        total_bad += bad
        print("   %-14s 卡片 %d（已长 %d / 本轮新增 %d）｜ 指针 过 %d / 不过 %d"
              % (skill, len(items), len(items) - len([x for x in items if x[0]['id'] not in have]),
                 len(new_items), ok, bad))
        for card, o, b, reasons in new_items:
            if b:
                print("        ✗ %s 回验不过：%s" % (card["id"], "；".join(reasons[:2])))
        rows.append((skill, cfg, new_items))

    if not apply:
        print("   ── 预演结束，未落盘 ──")
        return 0
    if total_bad:
        print("   ✗ 有指针回验不过 ⇒ **整轮不写**（宁可少长，不许长错）")
        return 1

    # 备份 → 写 → 同步 → 体检 → 失败回滚
    backup = os.path.join(ROOT, "kb/l8/_backups", "skill-growth-%s" % round_id)
    os.makedirs(backup, exist_ok=True)
    touched = []
    for skill, cfg, items in rows:
        if not items:
            continue
        src = cfg["source"]
        slot = os.path.join(SLOT, cfg.get("dir_name", skill))
        ref = os.path.join(src, "references", REF_NAME)
        led = os.path.join(src, "references", LEDGER_NAME)
        # ① 备份
        os.makedirs(os.path.join(backup, skill), exist_ok=True)
        for p in (ref, led):
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(backup, skill, os.path.basename(p)))
        # ② 追加 references（只追加）
        body = []
        for card, o, b, reasons in items:
            body.append("## %s · %s（%s 自动生长）" % (card["id"], card["主题"], stamp))
            body.append("")
            body.append("三重验证：score **%s** → **%s**；独立佐证 %d 个会话。"
                        % (card["三重验证"]["score"], card["三重验证"]["verdict"],
                           card["三重验证"].get("跨会话数", 0)))
            body.append("")
            for kind in ("可执行动作", "禁止动作", "风险点"):
                its = [i for i in card["条目"] if i["类"] == kind]
                if not its:
                    continue
                body.append("### %s" % kind)
                body.append("")
                for i, it in enumerate(its, 1):
                    body.append("%d. %s" % (i, it["动作"]))
                    for p in it["依据"]:
                        body.append("   - 依据 `%s` @ `%s` —— 「%s」"
                                    % (p["case_id"], p.get("anchor", "-"), p.get("quote", "")))
                body.append("")
        _, changed = append_block(ref, "<!-- skill-growth:%s -->" % items[0][0]["id"],
                                  "\n".join(body), "<!-- skill-growth:%s -->" % items[0][0]["id"])
        # ③ 同步装载位（从源 cp -p，不直接写装位）
        sync_to_slot(src, slot, [os.path.join("references", REF_NAME)])
        touched.append((skill, src, slot))
        print("   ✔ %s 追加 %d 张卡片" % (skill, len(items)))

    # ④ 体检
    groups, cerr = run_skills_check()
    n3 = class3_count(groups)
    if n3 is None:
        print("   ⚠ 未测：skills_check 读数取不到（%s）⇒ **回滚**" % cerr)
        n3 = -1
    ok_all = (n3 == 0)
    if not ok_all:
        print("   ✗ skills_check 第 3 类 = %s（应为 0）⇒ **回滚**" % n3)
        for skill, cfg, items in rows:
            if not items:
                continue
            for p in (os.path.join(cfg["source"], "references", REF_NAME),
                      os.path.join(cfg["source"], "references", LEDGER_NAME)):
                b = os.path.join(backup, skill, os.path.basename(p))
                if os.path.exists(b):
                    shutil.copy2(b, p)
                elif os.path.exists(p):
                    os.unlink(p)
            sync_to_slot(cfg["source"], os.path.join(SLOT, cfg.get("dir_name", skill)),
                         [os.path.join("references", REF_NAME)])
    else:
        print("   ✔ skills_check 第 3 类 = 0")

    # ⑤ 记台账（回滚了也记 —— 「试过、被谁拦、为什么」本身就是知识）
    for skill, cfg, items in rows:
        if not items:
            continue
        led = os.path.join(cfg["source"], "references", LEDGER_NAME)
        ok = sum(x[1] for x in items)
        append_ledger(led, "| %s | %s | %d | %d | 0 | %s | %s |"
                      % (stamp, round_id, len(items), ok, n3,
                         "已生长" if ok_all else "回滚（体检红）"))
        sync_to_slot(cfg["source"], os.path.join(SLOT, cfg.get("dir_name", skill)),
                     [os.path.join("references", LEDGER_NAME)])
    return 0 if ok_all else 1


# ── 反向对照 ────────────────────────────────────────────────────────
def selftest():
    fails, n = [], [0]

    def ck(name, got, want):
        n[0] += 1
        if got != want:
            fails.append("%s：得到 %r，期望 %r" % (name, got, want))

    cases = {"SC-1": {"case_id": "SC-1", "ask": "有问题要先修复再跑", "next_human": "怎么会这样"}}
    judged = {"SC-1": {"case_id": "SC-1", "判定": "反例"}}
    good = {"id": "SCH-1", "条目": [{"类": "禁止动作", "动作": "x",
                                     "依据": [{"case_id": "SC-1", "quote": "有问题要先修复再跑"}]}]}
    ck("T1 真卡片过", verify_card(good, cases, judged)[:2], (1, 0))
    # T2 ★ 改一个字的引文必须红（自生长的唯一硬闸门）
    bad_q = json.loads(json.dumps(good))
    bad_q["条目"][0]["依据"][0]["quote"] = "有问题要先修复再跑啊"
    ck("T2 引文改一字必红", verify_card(bad_q, cases, judged)[1], 1)
    # T3 幽灵 case
    ghost = json.loads(json.dumps(good))
    ghost["条目"][0]["依据"][0]["case_id"] = "SC-9"
    ck("T3 幽灵 case 必红", verify_card(ghost, cases, judged)[1], 1)
    # T4 ★ 拿「待人工复核」当依据必须红（无指针即无判定）
    j2 = {"SC-1": {"case_id": "SC-1", "判定": "待人工复核"}}
    ck("T4 待复核不许当依据", verify_card(good, cases, j2)[1], 1)
    # T5 ★ 断言：本脚本**没有任何写 SKILL.md 的路径**。
    #   ★ 判据里的那个文件名**必须拆开拼** —— 第一版直接写了字面量，
    #     于是断言被**它自己那行测试代码**命中，永远为红。
    #     这是本项目第三次撞上「检查器被自己的文字绊倒」（前两次：`s6_patch.py` 的 T4、
    #     `verify_shouheng_ops.py` 的 C5），所以修法统一成一条：**判据的字面量不许出现在判据自己的扫描面上**。
    needle = "SKILL" + chr(46) + "md"
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    body = src.split("def selftest", 1)[0]          # ★ 只扫**非自证**部分
    body = re.sub(r'""".*?"""', "", body, flags=re.S)
    body = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    ck("T5 不含写 %s 的路径" % needle, needle in body, False)
    # T5b 反向对照：把针放进被扫的那段，断言必须**变红**（否则 T5 恒真）
    ck("T5b 针在扫描面上必须红", needle in (body + "\nopen('%s','w')" % needle), True)
    # T6 marker 去重：同一张卡片长两次只留一份
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "r.md")
        write_text(p, "head\n")
        _, c1 = append_block(p, "<!-- m -->", "AAA", "<!-- m -->")
        _, c2 = append_block(p, "<!-- m -->", "AAA", "<!-- m -->")
        ck("T6 首写生效", c1, True)
        ck("T6b 重写被去重", c2, False)
        ck("T6c 原文仍在", read_text(p).startswith("head"), True)
    # T8 ★ 解析不到汇总行 ⇒ 未测（**不许**当成通过）—— 这条防的就是「每晚静默失败」
    ck("T8 非汇总文本=未测", _parse_summary("随便一段没有任何汇总行的文本"), None)
    ck("T8b 空文本=未测", _parse_summary(""), None)
    ck("T8c 真汇总行能解析", _parse_summary("五类问题：1=0 2=0 3=0 4=0 5=0 ｜合计 0\n结论：全过。")["3"], 0)
    ck("T8d 结论也读出来",
       _parse_summary("五类问题：1=1 2=0 3=2 4=0 5=0\n结论：有红。")["结论全过"], False)
    # T8e 反向对照：clone 出来的 counts 喂给 class3_count 必须能数出来
    ck("T8e counts 能喂给 class3_count",
       class3_count(_parse_summary("五类问题：1=0 2=0 3=7 4=0 5=0")), 7)

    # T7 第 3 类数不出来时必须判「未测」而不是「通过」
    ck("T7 数不出来 = None", class3_count({}), None)
    ck("T7b 有数就数出来", class3_count({"3": ["a", "b"]}), 2)
    ck("T7c 0 就是 0", class3_count({"3": []}), 0)

    if fails:
        print("❌ skill_growth 自证未过（%d / %d 项）" % (len(fails), n[0]))
        for f in fails:
            print("   " + f)
        return 1
    print("✅ skill_growth 自证全过（%d 项反向对照）" % n[0])
    return 0


def show_rounds(policy, err):
    if err:
        print("✗ 未测：%s" % err)
        return 2
    any_row = False
    for skill, cfg in sorted(policy["skills"].items()):
        led = os.path.join(cfg["source"], "references", LEDGER_NAME)
        if os.path.exists(led):
            any_row = True
            print("── %s" % skill)
            print(read_text(led))
    if not any_row:
        print("（还没有任何生长记录）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rounds", action="store_true")
    ap.add_argument("--pkg", default=None, help="候选包目录（缺省取最新的 会话蒸馏-*）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    policy, err = load_policy()
    if a.rounds:
        return show_rounds(policy, err)
    if err:
        print("✗ 未测：%s" % err)
        return 2
    pkg = a.pkg
    if not pkg:
        dirs = find_candidate_dirs()
        if not dirs:
            print("✗ 未测：找不到任何 `PMO/会话蒸馏-*` 候选包")
            return 2
        pkg = dirs[0]
    return grow(pkg, policy, a.apply)


if __name__ == "__main__":
    sys.exit(main())
