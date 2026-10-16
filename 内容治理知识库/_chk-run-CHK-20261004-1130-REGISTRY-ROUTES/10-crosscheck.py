# -*- coding: utf-8 -*-
"""独立交叉核对：skills.yaml(登记表) <-> routes.yaml(路由表) <-> layers.yaml(层契约) <-> 装载位实目录。
只读。不写 kb/。"""
import io, json, os, re, sys
import yaml

ROOT = "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
KB   = os.path.join(ROOT, "kb")
SK   = os.path.join(KB, "l7/registry/skills.yaml")
RT   = os.path.join(KB, "l7/registry/routes.yaml")
LY   = os.path.join(KB, "l7/registry/layers.yaml")
SLOT = os.path.expanduser("~/.dsh/skills")

out = []
def P(*a):
    out.append(" ".join(str(x) for x in a))

sk_doc = yaml.safe_load(open(SK, encoding="utf-8"))
rt_doc = yaml.safe_load(open(RT, encoding="utf-8"))
ly_txt = open(LY, encoding="utf-8").read()

rows = sk_doc["skills"]
ids     = {r.get("id") for r in rows}
dir2id  = {r.get("dir_name"): r.get("id") for r in rows if r.get("dir_name")}
id2dir  = {r.get("id"): r.get("dir_name") for r in rows if r.get("dir_name")}
idrow   = {r.get("id"): r for r in rows}

P("== 登记表基线 ==")
P("skills.yaml 行数:", len(rows))
own = [r for r in rows if r.get("scope") == "本项目"]
P("scope=本项目:", len(own), "| 其中 status=生产:", len([r for r in own if r.get("status") == "生产"]))
kbstar    = sorted(i for i in ids if i and i.startswith("kb-"))
brandstar = sorted(i for i in ids if i and i.startswith("brand-"))
P("id 前缀 kb-*:", len(kbstar), kbstar)
P("id 前缀 brand-*:", len(brandstar))
P("prefix brand-* =", brandstar)

P("")
P("== A. routes.yaml -> skills.yaml（id 存在性，独立复算）==")
prob = []
for r in rt_doc.get("routes") or []:
    t = r.get("to")
    if t not in ids:
        prob.append(("routes.to 不在登记表", r.get("intent"), t))
for c in rt_doc.get("chains") or []:
    if c.get("entry") not in ids:
        prob.append(("chains.entry 不在登记表", c.get("id"), c.get("entry")))
    for m in c.get("members") or []:
        if m not in ids:
            prob.append(("chains.members 不在登记表", c.get("id"), m))
for p in rt_doc.get("mutual_not_for") or []:
    for m in p.get("pair") or []:
        if m not in ids and m not in dir2id:
            prob.append(("mutual_not_for.pair 不在登记表(既非 id 也非 dir_name)", None, m))
for i in prob:
    P("  ✗", i)
P("  A 小计问题:", len(prob))

P("")
P("== B. frozen_expectation.dir_name_map: key 在登记表? value == skills.yaml 的 dir_name? ==")
fem = (rt_doc.get("frozen_expectation") or {}).get("dir_name_map") or {}
badk, badv = [], []
for k, v in fem.items():
    if k not in ids:
        badk.append(k)
    if id2dir.get(k) != v:
        badv.append((k, "routes.yaml 写", v, "skills.yaml 写", id2dir.get(k)))
P("  条目数:", len(fem))
P("  key 不在登记表的:", badk)
P("  value 与 skills.yaml.dir_name 不一致的:", badv)
reg_brand = sorted(i for i in brandstar)
P("  登记表里 brand-* 共", len(reg_brand), "｜dir_name_map 覆盖", len(fem),
  "｜未覆盖:", [b for b in reg_brand if b not in fem], "｜多余:", [k for k in fem if k not in ids])

P("")
P("== C. 登记表里「装了但任何路由/链都不指它」的成员（孤儿）==")
reach = set()
for r in rt_doc.get("routes") or []:
    reach.add(r.get("to"))
for c in rt_doc.get("chains") or []:
    reach.add(c.get("entry")); reach.update(c.get("members") or [])
P("  被 routes/chains 点到的 id 数:", len(reach))
orph = sorted(i for i in ids if i not in reach)
P("  登记表里没被点到的 id（%d 个）:" % len(orph), orph)

P("")
P("== D. layers.yaml 各层 skill: 字段 vs 登记表 vs 装载位 ==")
lay = re.findall(r"^- layer: (\S+)\n(?:.*\n)*?^  skill: \[([^\]]*)\]", ly_txt, re.M)
seen = set()
for lid, s in lay:
    ss = [x.strip() for x in s.split(",") if x.strip()]
    P("  %-3s skill=%s" % (lid, ss))
    for x in ss:
        seen.add(x)
        if x not in ids:
            P("      ✗ %s 不在 skills.yaml" % x)
        if not os.path.isdir(os.path.join(SLOT, id2dir.get(x) or x)):
            P("      ✗ %s 装载位无目录" % x)
P("  layers.yaml 引用的 skill 数:", len(seen))
P("  layers.yaml 引用但不在 routes.yaml 任何 to/chains 里的:",
  sorted(x for x in seen if x not in reach))

P("")
P("== E. 装载位实目录 vs 登记表 dir_name ==")
slot = sorted(d for d in os.listdir(SLOT) if os.path.isdir(os.path.join(SLOT, d)))
P("  装载位目录数:", len(slot))
missing = sorted(i for i in ids if id2dir.get(i) and not os.path.isdir(os.path.join(SLOT, id2dir[i])))
P("  登记了 dir_name 但装载位没有的:", missing)
unreg = sorted(d for d in slot if d not in dir2id and d not in ids)
P("  装载位有目录但登记表没有该 dir_name/id 的:", unreg)

P("")
P("== F. 赢家表里的名字 vs 登记名 ==")
wp = os.path.join(ROOT, "_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt")
wnames = set()
for line in open(wp, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"): continue
    for x in line.split("|")[1:4]:
        wnames.add(x.strip())
P("  赢家表出现过的取值:", sorted(wnames))
P("  其中既不是登记 id 也不是登记 dir_name 的:",
  sorted(w for w in wnames if w not in ids and w not in dir2id))

P("")
P("== G. 「让位表」到底在哪个文件（routes.yaml 被指为出处）==")
rev = os.path.join(KB, "l7/skills/kb-review/SKILL.md")
P("  routes.yaml 第 81 行写「见 kb-review 的让位表」；routes.yaml 自身含 '让位表' 的行:",
  [n for n, l in enumerate(open(RT, encoding="utf-8"), 1) if "让位表" in l])
P("  kb-review/SKILL.md 是否存在:", os.path.isfile(rev))
if os.path.isfile(rev):
    t = open(rev, encoding="utf-8").read()
    P("  kb-review/SKILL.md 含 '让位表' 的行号:",
      [n for n, l in enumerate(t.splitlines(), 1) if "让位表" in l])
P("  routes.yaml 顶层键:", list(rt_doc.keys()))

print("\n".join(out))
