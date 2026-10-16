#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 build-testcases-html.py 需要的 results.json（顶层 {id: {...}}）。

回复字段 = 被测会话当轮**实际写下的判定理由原文**（why），逐字取自会话产物，不编造。
本轮未采集「每条每轮的 AI 完整回复全文」→ 这一点已在 YAML 与报告中如实登记，
因此不声称通过原文自检；这里只是把可获得的真实文本按官方位置放进去。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
cases = json.load(open(os.path.join(BASE, 'a-cases.json'), encoding='utf-8'))['cases']
by = {str(c['id']): c for c in cases}


def load(f):
    out = {}
    for ln in open(f, encoding='utf-8'):
        ln = ln.strip()
        if ln:
            o = json.loads(ln)
            out[str(int(o['id']))] = (o.get('skill') or '', (o.get('why') or '').strip())
    return out


def expected_of(c):
    t, i = c['type'], c['id']
    if t == '正例':
        return '应触发 kb-check'
    if t == '调用':
        return '应加载 kb-check，然后追问' if i == 53 else ('不应加载 kb-check' if i == 52 else '应加载 kb-check')
    return '不应触发 kb-check'


def concl(c, skill_field):
    if c['type'] == '调用':
        return '加载' if skill_field == 'kb-check' else '未加载'
    return '触发' if skill_field == 'kb-check' else '不触发'


def build(slot, files):
    rounds = [load(f) for f in files]
    out = {}
    for cid, c in by.items():
        rr = []
        for r in rounds:
            sk, why = r.get(cid, ('', ''))
            rr.append({"结论": concl(c, sk), "回复": f"判定：{sk}｜理由：{why}"})
        out[cid] = {"标题": c['title'], "类型": c['type'], "提示词": c['prompt'],
                    "预期结果": expected_of(c), "标签": c.get('tags', ''),
                    "优先级": c.get('priority', ''), "轮次": rr}
    p = os.path.join(BASE, f'testcases_input_{slot}.json')
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return p


if __name__ == '__main__':
    a = [os.path.join(BASE, 'harness/A/round1.json'), os.path.join(BASE, 'harness/A/round2.json'),
         os.path.join(BASE, 'harness/A/round3b.json')]
    b = [os.path.join(BASE, f'harness/B/round{r}.json') for r in (1, 2, 3)]
    print(build('A', a))
    print(build('B', b))
