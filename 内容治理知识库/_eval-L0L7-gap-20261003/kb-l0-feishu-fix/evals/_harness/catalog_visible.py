#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确复刻 @deepseek-ai/dsh-tool-skill 的 catalogDescription：
     normalized = value.replaceAll(/\\s+/g," ").trim()
     return normalized.length <= max ? normalized : normalized[:max-3] + "..."
即：**先折叠空白再按 500 截断**（不是按 YAML 原文位置）。
"""
MAXLEN = 500
def render(desc, maxlen=MAXLEN):
    n = " ".join(desc.split())          # 等价于 /\s+/g -> " " 再 trim
    return n if len(n) <= maxlen else n[:maxlen-3] + "..."
def report(desc, rules, maxlen=MAXLEN):
    n = " ".join(desc.split())
    vis = render(desc, maxlen)
    print(f"折叠后总长 = {len(n)}  | 渲染长度 = {len(vis)} | 截断 = {len(n)>maxlen}")
    print(f"可见区（路由器实际看到）= 前 {len(vis)-3 if len(n)>maxlen else len(vis)} 字\n")
    print(f"{'规则':<28}{'首次出现位置':>12}  {'可见?':<6}")
    print("-"*52)
    bad=[]
    for label, needle in rules:
        i = n.find(needle)
        pos = i if i>=0 else None
        ok = (i>=0 and i < (maxlen-3 if len(n)>maxlen else maxlen))
        if pos is None: ok=False
        print(f"{label:<28}{('' if pos is None else pos):>12}  {'✅' if ok else '❌ 不可见'}")
        if not ok: bad.append(label)
    print()
    print("可见区末尾 120 字：", vis[-120:])
    return bad
