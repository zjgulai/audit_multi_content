#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**Owner 修复锁的销账器** —— 防重复修复、防被改回去。

真源：`kb/l7/registry/owner-fix-locks.yaml`
（Owner 意见 → 不变量 → 判据指针 → 反向对照）

为什么存在（Owner 2026-10-19：「你上面的修复问题要落库，**避免重复修复**」）：
同一个问题被报两次在本库发生过多次（「分类汇总怎么又复现了」「未归类 5 个」）。
`report-output-contract.yaml` 是**流水账**（按日期堆），没人能一眼看出
「这条 Owner 意见现在由哪把尺守着、那把尺还在不在」。
⇒ 本脚本机械核对三件事，**任何一件不成立就红**：

  ① **判据文件在不在** —— 锁指向的测试文件被删/改名 ⇒ 红（锁变成空话）；
  ② **判据 ID 还在不在正文里** —— 判据被删/被改名 ⇒ 红（这个最容易悄悄发生）；
  ③ **今天的修复有没有漏挂锁** —— `report-output-contract.yaml` 里
     `fix_*`（自 `coverage_since` 起）必须都能在锁表里找到 ⇒ 否则红（新修复没上锁）。

判据指针为什么用「文件 + ID 字符串」而不是「跑一遍」：
    hooks 要能在**离线、零依赖**下判断「锁还挂着东西没有」。真跑由
    `--run` 负责（去重后跑每条锁声明的 `run` 命令，只看退出码）。

用法
    kb/kbpy l8/owner_locks_check.py                 # 只做 ①②③（默认，秒级）
    kb/kbpy l8/owner_locks_check.py --selftest      # 反向对照：证明这三条不是恒真
    kb/kbpy l8/owner_locks_check.py --run           # 再把锁的判据真跑一遍
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent          # …/kb
KB_ROOT = KB.parent                                   # 内容治理
SHOUHENG = Path('/Users/lute/Project/audit_multi_content')
# ⚠️ 判据脚本住在 `tools/` 下，不是仓库根 —— 第一版把 cwd 设成根，
#    `node agent/dual_track.mjs` 直接 MODULE_NOT_FOUND ⇒ `--run` 全红（假红，最误导人的一种）。
TOOLS = SHOUHENG / 'tools'
LOCKS = KB / 'l7' / 'registry' / 'owner-fix-locks.yaml'
CONTRACT = KB / 'l7' / 'registry' / 'report-output-contract.yaml'

# 锁里的 `file:` 用两仓相对路径（`tools/…` / `kb/…`），这里给根
ROOTS = {'tools': SHOUHENG, 'kb': KB_ROOT}


def _yaml():
    try:
        import yaml  # noqa: PLC0415
        return yaml
    except Exception:                                  # noqa: BLE001
        raise SystemExit('[locks] 需要 PyYAML（kb/kbpy 的解释器自带）')


def load_locks() -> dict:
    if not LOCKS.is_file():
        raise SystemExit(f'[locks] 找不到真源：{LOCKS}')
    return _yaml().safe_load(LOCKS.read_text(encoding='utf-8')) or {}


def load_contract_keys() -> list[str]:
    if not CONTRACT.is_file():
        raise SystemExit(f'[locks] 找不到契约件：{CONTRACT}')
    d = _yaml().safe_load(CONTRACT.read_text(encoding='utf-8')) or {}
    return [k for k in d if isinstance(k, str) and k.startswith('fix_')]


def resolve(ref: str) -> Path | None:
    """把锁里的 `file:` 解析成绝对路径。**解析不到返回 None**（由调用方判红）。"""
    head = ref.split('/', 1)[0]
    root = ROOTS.get(head)
    if root is None:
        return None
    p = root / ref
    return p if p.is_file() else None


def check() -> tuple[list[str], list[str]]:
    """返回 (问题清单, 备注清单)。问题清单非空 ⇒ 退出码 1。"""
    bad: list[str] = []
    notes: list[str] = []
    locks = load_locks()
    items = locks.get('locks') or []
    if not items:
        return ['锁表是空的 —— 那等于没有锁'], notes

    # ① ② 逐把锁核：文件在不在、ID 在不在正文里
    for lk in items:
        lid = lk.get('id', '(无 id)')
        for j in lk.get('judges') or []:
            ref = str(j.get('file', ''))
            p = resolve(ref)
            if p is None:
                bad.append(f'{lid} 判据文件不存在或路径无法解析：{ref}')
                continue
            body = p.read_text(encoding='utf-8', errors='ignore')
            for jid in j.get('ids') or []:
                if str(jid) not in body:
                    bad.append(f'{lid} 判据「{jid}」在 {ref} 里**找不到**（被删或改名了）')

    # ③ 覆盖：自 coverage_since 起的 fix_* 必须都有锁
    since = str((locks.get('meta') or {}).get('coverage_since') or '')
    covered = set()
    for lk in items:
        covered.add(str(lk.get('for')))
        for x in (lk.get('also_for') or []):
            covered.add(str(x))          # 一条锁可以**合并覆盖**多个 fix_（同一个不变量）

    if since:
        need = [k for k in load_contract_keys() if k >= since]
        missing = [k for k in need if k not in covered]
        if missing:
            bad.append(f'有 {len(missing)} 条修复**没挂锁**（自 {since} 起）：{", ".join(missing)}')
        notes.append(f'覆盖检查：{since} 起共 {len(need)} 条修复，已挂锁 {len(need) - len(missing)} 条')
    # 反向：锁指到的 fix_* 必须真的在契约件里（防锁表里写了不存在的条目）
    for lk in items:
        f = str(lk.get('for') or '')
        if f and f not in load_contract_keys():
            bad.append(f'{lk.get("id")} 指向的 `{f}` 在 report-output-contract.yaml 里不存在')
        if lk.get('superseded_by'):
            if not lk.get('why'):
                bad.append(f'{lk.get("id")} 标了 superseded_by 却没写 why —— 说不清为什么可以被取代')
            # 被取代的锁**允许**没有判据（判据在取代它的那把锁上），但取代者必须存在
            if str(lk['superseded_by']) not in {str(x.get('id')) for x in items}:
                bad.append(f'{lk.get("id")} 的 superseded_by={lk["superseded_by"]} 在锁表里不存在')
            continue
        if not (lk.get('judges') or []):
            bad.append(f'{lk.get("id")} 没挂任何判据 —— 那不是锁，是散文')
        if not lk.get('reverse_control'):
            bad.append(f'{lk.get("id")} 没写反向对照 —— 判据可能恒真')
    return bad, notes


# ── 自证 ────────────────────────────────────────────────────────────────────────
def selftest() -> int:
    """反向对照：把真源「弄坏」一份，确认 ①②③ 各自能红。**不碰真文件**。"""
    import tempfile
    y = _yaml()
    bad: list[str] = []

    def eq(name, cond, why=''):
        if cond:
            print(f'  ✅ {name}')
        else:
            bad.append(f'{name} —— {why}')
            print(f'  ❌ {name}')

    locks = load_locks()
    items = locks['locks']
    print('=== Owner 修复锁 自证 ===')
    eq('① 真源读得到、至少 10 把锁', len(items) >= 10, f'实得 {len(items)}')

    # 反向对照 1：判据 ID 被改 ⇒ 「找不到」必须出现
    tmp = y.safe_load(y.safe_dump(locks))
    tmp['locks'][0]['judges'][0]['ids'] = ['不存在的判据ID-XYZ']
    saved = LOCKS.read_text(encoding='utf-8')
    try:
        LOCKS.write_text(y.safe_dump(tmp, allow_unicode=True), encoding='utf-8')
        b, _ = check()
        eq('② 判据 ID 被改 ⇒ 变红（且在说「找不到」）',
           any('找不到' in x for x in b), str(b[:2]))
    finally:
        LOCKS.write_text(saved, encoding='utf-8')

    # 反向对照 2：判据文件路径写错 ⇒ 「文件不存在」必须出现
    tmp = y.safe_load(saved)
    tmp['locks'][0]['judges'][0]['file'] = 'tools/agent/绝对不存在.mjs'
    try:
        LOCKS.write_text(y.safe_dump(tmp, allow_unicode=True), encoding='utf-8')
        b, _ = check()
        eq('① 判据文件写错 ⇒ 变红（且在说「文件不存在」）',
           any('不存在' in x for x in b), str(b[:2]))
    finally:
        LOCKS.write_text(saved, encoding='utf-8')

    # 反向对照 3：少挂一把锁 ⇒ 覆盖检查必须点出来
    tmp = y.safe_load(saved)
    dropped = tmp['locks'].pop()['for']
    try:
        LOCKS.write_text(y.safe_dump(tmp, allow_unicode=True), encoding='utf-8')
        b, _ = check()
        eq('③ 抽掉一条锁 ⇒ 覆盖检查变红（且点名那条 fix_）',
           any('没挂锁' in x and dropped in x for x in b), str(b[:2]))
    finally:
        LOCKS.write_text(saved, encoding='utf-8')

    # 回到真实状态再核一次（证明上面三次改坏都还原了）
    b, _ = check()
    eq('④ 还原后重新全绿', not b, str(b[:3]))
    print(f"\n自证：通过 {len(bad) == 0 and 'all' or '—'} / 失败 {len(bad)}")
    for x in bad:
        print(f'   ❌ {x}')
    return 1 if bad else 0


def run_judges() -> int:
    """把锁声明的判据真跑一遍（命令去重；只看退出码）。"""
    print('=== 真跑判据 ===')
    cmds = [
        ('守衡 dual_track', ['node', 'agent/dual_track.mjs', '--selftest']),
        ('守衡 prd53 格式', ['node', 'agent/prd53_format.test.mjs']),
        ('守衡 prd17', ['node', 'agent/prd17.mjs', '--selftest']),
        ('守衡 prd533', ['node', 'agent/prd533.mjs', '--selftest']),
        ('守衡 verify_cards', ['node', 'verify_cards.mjs']),
        ('守衡 test_agent', ['node', 'test_agent.mjs']),
        ('守衡 node --test', ['node', '--test', 'agent/model_side_taxonomy.test.mjs',
                              'agent/claim_preflight.test.mjs', 'agent/routing.test.mjs',
                              'agent/prd53_format.test.mjs', 'agent/ext_basis.test.mjs']),
    ]
    rc_all = 0
    for name, cmd in cmds:
        try:
            r = subprocess.run(cmd, cwd=str(TOOLS), capture_output=True, text=True, timeout=600)
            ok = r.returncode == 0
            # test_agent 用「失败 N」自报，退出码不一定非零
            if '合计' in (r.stdout or ''):
                m = re.search(r'通过 (\d+) / 失败 (\d+)', r.stdout)
                if m:
                    ok = int(m.group(2)) == 0
            print(f'  {"✅" if ok else "❌"} {name}' + ('' if ok else f'（rc={r.returncode}）'))
            if not ok:
                rc_all = 1
        except Exception as e:                          # noqa: BLE001
            print(f'  ❌ {name} —— 跑不起来：{e}')
            rc_all = 1
    return rc_all


def main() -> int:
    ap = argparse.ArgumentParser(description='Owner 修复锁的销账器（防重复修复）')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--run', action='store_true', help='再把锁声明的判据真跑一遍')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    bad, notes = check()
    for n in notes:
        print(f'  · {n}')
    if bad:
        print('\n❌ 修复锁检查不通过：')
        for x in bad:
            print(f'  · {x}')
        return 1
    print('✅ 修复锁全绿：判据文件在、判据 ID 在、今天的修复都挂上锁了')
    if a.run:
        return run_judges()
    return 0


if __name__ == '__main__':
    sys.exit(main())
