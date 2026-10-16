#!/usr/bin/env python3
"""核对飞书表里这 5 个字段**彼此对齐**、且**与 `10/14重跑报告链接` 那份报告对齐**：

    Agent 结论 ／ 置信度 ／ 问题数量 ／ 问题分类汇总 ／ 10/14重跑报告链接

Owner 2026-10-14：「这些字段的数据要对齐的。全部跑完后检查。」

── 为什么要有这把尺子（不是「看着差不多」）
这 5 格有 **4 个产者**，各写各的：
  · `Agent 结论`／`问题数量`／`置信度` ← 守衡 `review_publish.mjs` 从链/旁挂读数派生；
  · `问题分类汇总`                  ← 守衡**另拼一份**（抬头 ＋ 卡内总数 ＋ 逐条留痕）；
  · `10/14重跑报告链接`             ← 跟随器从**台账**写；
  · 报告云文档                      ← 链自己发布。
⇒ 同一件事有四个落点，**没有一个地方保证它们相等**。实测过的形状：卡片抬头写 PASS、
  表里那格是 NEEDS_INPUT；`问题数量` 按卡内总数记、而库侧机器读数是另一个数
  （Owner 2026-10-09 定「按卡里那个数」）—— 两条并存**不算错，但必须说出来**。

── 逐条判据（每条都能指出「谁跟谁不等」，不写模糊话）
  M1  `10/14重跑报告链接` 取不出令牌 / 报告没拉下来        ⇒ 无从核对（**未测**，不是通过）
  M2  `Agent 结论` ≠ 报告里的 `【审查结论：X】`             ⇒ 两个结论
  M3  `问题数量`   ≠ 报告里的 `共发现 N 处`                 ⇒ 数与报告不符（Owner 点名要对的这一条）
  M4  报告自身不闭合：`共发现 N 处` ≠ 报告里逐条编号的条数   ⇒ 报告内部就自相矛盾
  M5  `问题分类汇总` 里的「卡内总数 N 处」 ≠ `问题数量`      ⇒ 同表两格两个数
  M6  `问题分类汇总` 抬头里那个「报告：」链接 ≠ `10/14重跑报告链接` ⇒ 汇总指旧报告、链接指新报告
  M7  `置信度 = 0` 而汇总里**没有** 0 的口径说明            ⇒ 0 会被读成「零风险」
  M8  `置信度` 不在 (0,1] 且 ≠ 0                            ⇒ 不是一个置信度
  M9  汇总里【逐条依据】的条数 ≠ `问题数量`                  ⇒ 列了 5 条却说 6 处（除非写明「另有 N 条」）

用法：
  python3 align_fields80.py                 # 只报
  python3 align_fields80.py --json out/align80.json
"""
import argparse, glob, html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE = 'RY2UbCRjXaeeWwscUPScVN5AnQc'
TABLE = 'tblavfbMDMeRsulo'

NEW_COL = '10/14重跑报告链接'


def plain(cell):
    """把单元格拍成字符串（字符串 / 富文本段数组 / 数字都吃）。"""
    if cell is None:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, (int, float)):
        return str(cell)
    if isinstance(cell, list):
        out = []
        for seg in cell:
            if isinstance(seg, dict):
                out.append(str(seg.get('text') or seg.get('link') or ''))
            else:
                out.append(str(seg))
        return ''.join(out)
    if isinstance(cell, dict):
        return str(cell.get('text') or cell.get('link') or '')
    return str(cell)


def fetch_table():
    r = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--page-size', '200', '--format', 'json', '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print('拉表失败：', r.stderr[:300]); sys.exit(2)
    d = json.loads(r.stdout)['data']
    return d['fields'], d['data'], d.get('record_id_list') or d.get('record_ids') or []


def doc_text(path):
    d = json.load(open(path, encoding='utf-8'))
    c = (d.get('data') or {}).get('document', {}).get('content') or ''
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def report_feats(t):
    f = {}
    m = re.search(r'【审查结论：(\w+)】', t)
    f['state'] = m.group(1) if m else None
    m = re.search(r'共发现\s*(\d+)\s*处', t)
    f['declared'] = int(m.group(1)) if m else None
    f['items'] = len(re.findall(r'(?m)^\s*(\d+)[.、]\s*【', t))
    f['cats'] = re.findall(r'(?m)^\s*\d+[.、]\s*【([^】]{1,20})】', t)
    return f


def link_token(s):
    m = re.search(r'/(?:docx|docs)/([A-Za-z0-9]{20,})', str(s or ''))
    return m.group(1) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=os.path.join(OUT, 'align80.json'))
    a = ap.parse_args()

    fields, rows, _ = fetch_table()
    idx = {f: i for i, f in enumerate(fields)}
    G = lambda r, k: r[idx[k]] if idx.get(k) is not None and idx[k] < len(r) else None

    cases, problems, norep, refetched = [], [], [], []
    for r in rows:
        cid = plain(G(r, '内容 ID')).strip()
        concl = plain(G(r, 'Agent 结论')).strip()
        conf_raw = G(r, '置信度')
        conf = None
        try:
            conf = float(plain(conf_raw)) if plain(conf_raw) != '' else None
        except ValueError:
            conf = None
        cnt_raw = plain(G(r, '问题数量')).strip()
        try:
            cnt = int(float(cnt_raw)) if cnt_raw != '' else None
        except ValueError:
            cnt = None
        summ = plain(G(r, '问题分类汇总'))
        tok = link_token(G(r, NEW_COL))

        rp = os.path.join(OUT, 'reports_new', f'{cid}.json')
        # ══════════════════════════════════════════════════════════════════════════
        # ★★ 2026-10-15：**链接换了就重拉报告** —— 缓存按「内容 ID」命名，而链接列会被
        #   复跑 / 跟随器 / 手工改。旧行为只读缓存 ⇒ 拿一份**已经不在链接列**的旧报告去核，
        #   于是报**幻红**。实测两次（都不是数据坏了，是尺子读错了）：
        #     · 第70行补上新链接后 → 报 M2/M3（读的是更早那份「REVIEW/1 处」的文档）；
        #     · black-friday 换新报告后 → 报 M3（问题数量 4 ≠ 缓存里那份的「共发现 6 处」）。
        #   判据 = 缓存里的 `document_id` 与链接列令牌**逐字相同**；不同就重拉、原样覆盖缓存。
        #   （`lark-cli docs +fetch --json` 的返回里就带 `document_id`，不必另存一份映射。）
        if tok:
            cached_doc = None
            if os.path.exists(rp):
                try:
                    cached_doc = (((json.load(open(rp, encoding='utf-8')).get('data') or {})
                                   .get('document') or {}).get('document_id'))
                except Exception:
                    cached_doc = None
            if cached_doc != tok:
                q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb',
                                    '--as', 'bot', '--json'], capture_output=True, text=True)
                try:
                    j = json.loads(q.stdout)
                    if (((j.get('data') or {}).get('document') or {}).get('content')):
                        open(rp, 'w', encoding='utf-8').write(json.dumps(j, ensure_ascii=False))
                        refetched.append(f'{cid}({cached_doc or "无缓存"}→{tok})')
                except Exception:
                    pass                                     # 拉不到就当没有（下面按 rf=None 走 M1）
        rf = report_feats(doc_text(rp)) if os.path.exists(rp) else None

        # ══════════════════════════════════════════════════════════════════════════
        # ★★ 2026-10-15：**这一格的形状换了**（Owner 裁定：按 PRD §5.3 出摘要、覆盖旧值）
        # ──────────────────────────────────────────────────────────────────────────
        #   旧形状：`卡内总数 N 处（库侧 X ＋ 模型侧 Y）…` ＋【逐条依据（落库留痕）】
        #   新形状：结论行 → `· <大类>类问题：N 个` → `→ 查看完整问题清单与修改建议：<链接>`
        #           → 动作行 →【逐条依据（落库留痕）】→ ⚠️ 口径说明
        #   ⇒ 旧判据里**读旧形状**的两条（M5 卡内总数、M5b 缺该句）随之作废，
        #     换成同义的**新形状**判据（M5′ 分类计数闭合）；并补三条新形状才有的：
        #     M10 格里的结论行必须与 `Agent 结论` 一致（旧格里根本没有结论行，无从核）；
        #     M11 每一条依据要么带 url、要么显式标注「无库内依据」（Owner 2026-10-15 第 2 条）；
        #     M12 动作行必须与三态匹配（PRD §5.3.2/§5.3.3 的收尾句）。
        s_items = len(re.findall(r'(?m)^\s*(\d+)[.、]\s*【', summ))
        s_link = (link_token(re.search(r'查看完整问题清单与修改建议：\s*(\S+)', summ).group(1))
                  if re.search(r'查看完整问题清单与修改建议：\s*(\S+)', summ) else None)
        s_other = re.search(r'另有\s*\**\s*(\d+)\s*\**\s*条', summ)
        s_head = re.search(r'【审查结论：(\w+)】共发现\s*(\d+)\s*处', summ)
        s_bullets = re.findall(r'·\s*([^·\n]{1,18}?)类问题：\s*(\d+)\s*个', summ)
        s_summed = sum(int(n) for _, n in s_bullets) + (int(s_other.group(1)) if s_other else 0)
        s_noitem = '没有并进任何' in summ
        s_action = re.search(r'(请修改后重新提交。|建议转 @[^\n]*?复核。)', summ)

        bad = []
        if not tok or rf is None:
            # ⚠️ 2026-10-14 **收窄**（原来一律判 M1）：**问题数量为 0 的单子本来就不建报告**
            #   （PRD §5.3.4：报告门槛是「有问题」）。实测触发：`MC-US-WEB-IMG-8435496550598`
            #   重跑后模型侧 0 条 ⇒ 合并 0 条 ⇒ 不建报告 ⇒ 链接列空。那是**对的**，不是缺陷。
            #   ⇒ 有 N>0 处问题却没有报告可核，才算 M1。
            if cnt:
                bad.append(('M1', f'有 {cnt} 处问题却没有报告可核（tok={tok or "—"}）'))
            else:
                norep.append(cid)
        else:
            if concl and rf['state'] and concl != rf['state']:
                bad.append(('M2', f'Agent 结论={concl} ≠ 报告【审查结论：{rf["state"]}】'))
            if cnt is not None and rf['declared'] is not None and cnt != rf['declared']:
                bad.append(('M3', f'问题数量={cnt} ≠ 报告「共发现 {rf["declared"]} 处」'))
            if rf['declared'] is not None and rf['declared'] != rf['items']:
                bad.append(('M4', f'报告自身不闭合：共发现 {rf["declared"]} 处 ≠ 逐条编号 {rf["items"]} 条'))
        # ── 新形状判据 ──────────────────────────────────────────────────────────
        if cnt and not s_head:
            bad.append(('M10', f'问题数量={cnt}，但格首没有 PRD 结论行（【审查结论：X】共发现 N 处）'))
        elif s_head and concl and s_head.group(1) != concl:
            bad.append(('M10', f'格里的结论行【审查结论：{s_head.group(1)}】 ≠ Agent 结论 {concl}'))
        elif s_head and cnt is not None and int(s_head.group(2)) != cnt:
            bad.append(('M10', f'结论行「共发现 {s_head.group(2)} 处」 ≠ 问题数量 {cnt}'))
        if cnt and s_bullets and s_summed != cnt and not s_noitem:
            bad.append(('M5', f'分类计数 {s_summed} 个 ≠ 问题数量 {cnt}（没写「另有 N 条」也没写「没有并进任何」）'))
        if cnt and cnt >= 3 and not s_bullets and not s_noitem:
            bad.append(('M5b', f'问题数量 {cnt} ≥3，却没有 PRD 要求的「· XX类问题：N 个」分类块'))
        if s_link and tok and s_link != tok:
            bad.append(('M6', f'格里的报告链接 {s_link} ≠ {NEW_COL} {tok}'))
        if conf == 0 and not re.search(r'按 \*\*0\*\* 记|不是「零风险」|未做判定|没读到引擎读数', summ):
            bad.append(('M7', '置信度=0，但汇总里没有 0 的口径说明'))
        if conf is not None and conf != 0 and not (0 < conf <= 1):
            bad.append(('M8', f'置信度={conf} 不在 (0,1]'))
        if cnt is not None and cnt and s_items and s_items != cnt and not s_other and not s_noitem:
            bad.append(('M9', f'汇总逐条依据 {s_items} 条 ≠ 问题数量 {cnt}（且没写「另有 N 条」）'))
        if concl and concl != 'PASS' and not s_action:
            bad.append(('M12', '缺动作行（PRD §5.3.2/§5.3.3 的「建议转 @… 复核。」／「请修改后重新提交。」）'))
        # M11：Owner 2026-10-15 第 2 条 —— 逐条依据每条要么带 url，要么显式标注无依据（不许编）
        if s_items:
            blocks = re.split(r'(?m)^\s*\d+[.、]\s*', summ.split('【逐条依据（落库留痕）】')[-1])[1:]
            no_ev = [b[:28] for b in blocks
                     if not re.search(r'https?://', b) and not re.search(r'无库内依据|无库内条款|没有并进任何', b)]
            if no_ev:
                bad.append(('M11', f'{len(no_ev)} 条依据既没有 url 也没有「无库内依据」标注：{no_ev[:2]}'))

        rec = {'cid': cid, 'concl': concl, 'conf': conf, 'cnt': cnt,
               'sum_head': s_head.group(0) if s_head else None, 'sum_bullets': s_summed,
               'sum_items': s_items, 'tok': tok,
               'rep_state': (rf or {}).get('state'), 'rep_declared': (rf or {}).get('declared'),
               'rep_items': (rf or {}).get('items'), 'bad': bad}
        cases.append(rec)
        for code, why in bad:
            problems.append((code, cid, why))

    # ── 汇总 ──
    from collections import Counter
    cc = Counter(p[0] for p in problems)
    print(f'表内 {len(rows)} 行 ｜ 新版报告在手 {sum(1 for c in cases if c["tok"])} 份 ｜ '
          f'**有问题的行 {sum(1 for c in cases if c["bad"])} 行 / 问题 {len(problems)} 条**')
    if norep:
        print(f'（另有 {len(norep)} 行**本就不该有报告**：问题数量 0 ⇒ 按 PRD §5.3.4 不建报告：{norep}）')
    if refetched:
        # ★ 重拉是**正确行为**（链接换过），但必须看得见 —— 否则下一个人会以为
        #   「尺子读的就是链接列那份」，而这份判据最容易被缓存骗过去（2026-10-15 连踩两次）。
        print(f'（报告缓存与链接不一致 ⇒ **重拉 {len(refetched)} 份**：{refetched[:3]}'
              f'{" …" if len(refetched) > 3 else ""}）')
    print()
    print('按判据分类：')
    for k in sorted(cc):
        print(f'  {k:<4} {cc[k]:>3} 条')
    print()
    by = {}
    for code, cid, why in problems:
        by.setdefault(cid, []).append((code, why))
    for cid in sorted(by):
        print(f'── {cid}')
        for code, why in by[cid]:
            print(f'     [{code}] {why}')

    json.dump({'n_rows': len(rows), 'n_problems': len(problems), 'no_report_expected': norep,
               'by_code': dict(cc), 'cases': cases},
              open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n明细 → {a.json}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
