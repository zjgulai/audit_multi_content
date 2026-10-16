#!/usr/bin/env python3
"""解析「内容治理数据采集」表（80 行）—— **按表头驱动**，不写死列名。

## 为什么不能写死

第一版把列名与列序写死在代码里，于是表里**新加一列**（`10/14重跑报告链接`）之后，
尾部仍按「最后 3 列 = 产品线/送审版本/人工复核人」取值 ⇒ **整段错位，还会静默给出错值**
（实测：新列写进去的值被读成空，差点误判「写入失败」）。
⇒ 现在从表头 `| _record_id | … |` 那一行取列名；尾部有几列由表头决定。

## 两列含**未转义**的 `|`

  · `问题分类汇总` —— 实测写过正则 `perfect\\|zero[\\s-]?risk` ⇒ 一行被切成 25 段；
  · `采集数据`     —— 素材正文里带 `|`。

⇒ 锚点用**形态唯一**的 `报告链接`（`[..](https://…docx/…)`）：
   它左边前 4 列固定、第 5 列（问题分类汇总）吸多余段；
   右边除 `采集数据` 外全部固定。
"""
import json
import os
import re
import sys

REPORT_RE = re.compile(r'^\[.*\]\(https?://[^)]*docx/[^)]*\)$')


def header_of(path):
    for line in open(path, encoding='utf-8'):
        if line.startswith('| _record_id'):
            return [c.strip() for c in line.rstrip('\n').strip('|').split('|')]
    return None


def parse(path):
    hdr = header_of(path)
    if not hdr:
        return []
    N = len(hdr)
    rows = []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not re.match(r'^\|\s*rec[A-Za-z0-9]{11}\s*\|', line):
            continue
        p = [c.strip() for c in line.strip('|').split('|')]
        if len(p) < N:
            continue
        R = next((i for i, c in enumerate(p) if REPORT_RE.match(c)), None)
        if R is None:
            continue
        d = {}
        # ── 报告链接左侧：前 4 列逐一对应，第 5 列（问题分类汇总）吸掉多余的段 ──
        for i in range(min(4, R)):
            d[hdr[i]] = p[i]
        if R >= 5:
            d[hdr[4]] = '|'.join(p[4:R])
        d[hdr[R]] = p[R]
        # ── 报告链接右侧：按表头取名字，只有「采集数据」会吸多余段 ──
        tail = hdr[R + 1:]
        if not tail:
            rows.append(d)
            continue
        dirty = tail.index('采集数据') if '采集数据' in tail else -1
        if dirty < 0:
            for k, name in enumerate(tail):
                d[name] = p[R + 1 + k] if R + 1 + k < len(p) else ''
        else:
            for k in range(dirty):
                d[tail[k]] = p[R + 1 + k] if R + 1 + k < len(p) else ''
            after = len(tail) - dirty - 1
            end = len(p) - after if after else len(p)
            d['采集数据'] = '|'.join(p[R + 1 + dirty:end])
            for k in range(after):
                d[tail[dirty + 1 + k]] = p[len(p) - after + k]
        rows.append(d)
    return rows


def flat(v):
    v = (v or '').strip()
    if v.startswith('['):
        try:
            return ','.join(map(str, json.loads(v)))
        except Exception:
            return v
    return v


def doc_id(url):
    m = re.search(r'/docx/([A-Za-z0-9]+)', url or '')
    return m.group(1) if m else None


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'out/table80.txt')
    hdr = header_of(path)
    print('表头（%d 列）:' % len(hdr), hdr)
    rows = parse(path)
    print('行数:', len(rows))
    for r in rows:
        print(f"{r.get('_record_id')}  {r.get('内容 ID', ''):<40} "
              f"{flat(r.get('渠道')):<8} {r.get('产品线', ''):<6} "
              f"{flat(r.get('Agent 结论')):<12} 问题={flat(r.get('问题数量')) or '—':<3} "
              f"旧={doc_id(r.get('报告链接')) or '—'} 新={doc_id(r.get('10/14重跑报告链接')) or '—'}")
