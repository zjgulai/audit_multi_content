#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 harness 原始盲测判定转成 score-trigger-eval.py 接受的 results.json。

映射口径（固化）：
  skill 字段精确等于 "kb-check" → 触发；其余一切（别的 skill / 追问 / 不加载）→ 不触发。
  expected 按「本 skill 应该怎样」写，供脚本判四格：
    正例 1-16        → 应触发 kb-check
    负例/近似/边界   → 不应触发 kb-check
    边界 [40][42]    → 不应触发 kb-check（服务该请求不需要加载本 skill）
    调用 51/53       → 应加载 kb-check；52 → 不应加载 kb-check
  说明：调用行不进四格，由调用门槛单独判。
"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
cases = json.load(open(os.path.join(BASE, 'a-cases.json'), encoding='utf-8'))['cases']
by_id = {c['id']: c for c in cases}


def load(round_file):
    out = {}
    for ln in open(round_file, encoding='utf-8'):
        ln = ln.strip()
        if ln:
            o = json.loads(ln)
            out[int(o['id'])] = (o.get('skill') or '').strip()
    return out


def verdict(skill_field):
    return '触发' if skill_field == 'kb-check' else '不触发'


def call_verdict(skill_field):
    """调用题按官方口径记「加载 / 未加载」（不是 触发/不触发）。"""
    return '加载' if skill_field == 'kb-check' else '未加载'


def expected_of(c):
    t, i = c['type'], c['id']
    if t == '正例':
        return '应触发 kb-check'
    if t == '调用':
        return '应加载 kb-check，然后追问' if i == 53 else ('不应加载 kb-check' if i == 52 else '应加载 kb-check')
    return '不应触发 kb-check'


def build(slot, rounds):
    res = []
    for i in sorted(by_id):
        c = by_id[i]
        if c['type'] == '调用':
            r = [call_verdict(x.get(i, '')) for x in rounds]
        else:
            r = [verdict(x.get(i, '')) for x in rounds]
        res.append({"id": i, "type": c['type'], "expected": expected_of(c),
                    "tags": c.get('tags', ''), "rounds": r,
                    "title": c['title']})
    return {"skill_name": "kb-check", "version": slot, "results": res}


def main():
    out = {}
    for slot in ('A', 'B'):
        files = []
        for r in (1, 2, 3):
            f = os.path.join(BASE, 'harness', slot, f'round{r}.json')
            if os.path.exists(f):
                files.append(f)
        # A 第 3 轮原始产物因被测会话偷看答案键作废，改用干净重跑 round3b
        if slot == 'A':
            b3 = os.path.join(BASE, 'harness', 'A', 'round3b.json')
            if os.path.exists(b3):
                files = [os.path.join(BASE, 'harness', 'A', f'round{r}.json') for r in (1, 2)] + [b3]
        rounds = [load(f) for f in files]
        print(f"[{slot}] 采用轮次文件: {[os.path.basename(f) for f in files]}")
        obj = build(slot, rounds)
        p = os.path.join(BASE, f'results_{slot}.json')
        json.dump(obj, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        out[slot] = p
        # 一致性核对
        n_t = sum(1 for x in obj['results'] if x['rounds'][0] == '触发')
        print(f"{slot}: {len(rounds)} 轮, {len(obj['results'])} 条, 第1轮触发 {n_t} 条 -> {p}")
    return out


if __name__ == '__main__':
    main()
