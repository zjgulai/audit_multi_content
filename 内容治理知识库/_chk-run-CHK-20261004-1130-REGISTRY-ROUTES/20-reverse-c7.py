# -*- coding: utf-8 -*-
"""C7 的反向：登记表声明 layer=Lx 的成员，是否出现在 layers.yaml 该层 skill: 里。
C7 正读只查「层契约 → 登记表」，本脚本查「登记表 → 层契约」。只读。"""
import os, re, yaml
ROOT="/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
SK=os.path.join(ROOT,"kb/l7/registry/skills.yaml"); LY=os.path.join(ROOT,"kb/l7/registry/layers.yaml")
reg=yaml.safe_load(open(SK,encoding="utf-8"))["skills"]
lay=yaml.safe_load(open(LY,encoding="utf-8"))
print("layers.yaml 顶层键:", list(lay.keys()))
layers = lay["layers"] if "layers" in lay else lay
by={}
for L in layers:
    lid=L.get("layer"); s=L.get("skill") or []
    if isinstance(s,str): s=[s]
    by[str(lid)]=[str(x) for x in s]
print("\n层契约 skill 清单：")
for k in sorted(by): print("  %-3s %s" % (k, by[k]))

print("\n登记表里 scope=本项目 且 layer 是单一 Lx 的成员，是否在该层 skill: 清单里：")
bad=[]
for r in reg:
    if r.get("scope")!="本项目": continue
    lyr=str(r.get("layer") or "").strip()
    if not re.fullmatch(r"L[0-7]", lyr): continue
    inlist = r["id"] in by.get(lyr,[])
    tag = "✅" if inlist else "❌"
    if not inlist: bad.append((r["id"], lyr, r.get("status"), r.get("dir_name")))
    print("  %s %-28s layer=%-4s status=%s" % (tag, r["id"], lyr, r.get("status")))
print("\n❌ 反向不一致（登记表说在 Lx，层契约没列它）: %d 个" % len(bad))
for b in bad: print("   ", b)
