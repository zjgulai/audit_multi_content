#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_shouheng_basis_20261020.py —— 把「有依据」判成「能解析出登记来源」（守衡仓 · 双写校验）。

为什么要在本仓写、再跑到守衡仓：
  `_hasBasis` 住在 `/Users/lute/Project/audit_multi_content/tools/agent/model_side.mjs`，
  它不在本会话的工作区里 ⇒ 直接写会被沙箱拒绝（`Operation not permitted`，实测）。
  所以：脚本留在工作区（留痕 / 可重跑 / 可 review），执行只做**逐处精确替换 + 逐处校验**，
  任一处不匹配就**整体不落盘**（不做半成品补丁）。

修的是什么（Owner 2026-10-20 拿真卡来问那一单：AD-20261020-006）：
  卡上两条都印 `依据：独立语义复核（非条款依据，需人工核对）`，而 Owner 2026-10-19
  明令这句不许出现。根因不在渲染层：解析边界把**占位值**当成了依据 ——
    · `_hasBasis = !!String(raw.source).trim() || URL`  ⇒ `"none"` 这种非空占位词也算「有依据」；
    · 而提示词恰恰教模型「实在找不到依据，就写 `source:"none"`」。
  于是 `basis_missing=false` ⇒ 展示层的过滤器放行 ⇒ 卡面印出兜底句。

修法（三条，都是「同一把尺」而不是新口径）：
  ① `_hasBasis` 改用 `resolveSourceId()`（闭集 S1–S17，与渲染侧同一个函数）；
  ② URL 误写进 `source` 时**归一化**到 `source_url`（同一个字符串，不算发明，也不白丢一条）；
  ③ 提示词不再教占位值（源头关掉入口；解析侧是第二道）。

用法：
    python3 .work/patch_shouheng_basis_20261020.py           # 预演（只比对，不写）
    python3 .work/patch_shouheng_basis_20261020.py --apply   # 真写（逐处校验后落盘）
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import time

SH_REPO = os.environ.get("SHOUHENG_REPO") or "/Users/lute/Project/audit_multi_content"
MODEL_SIDE = os.path.join(SH_REPO, "tools/agent/model_side.mjs")
TEST_AGENT = os.path.join(SH_REPO, "tools/test_agent.mjs")


# ── ① model_side.mjs：依据判定改用 resolveSourceId ────────────────────────────
OLD_BASIS = """    const _hasBasis = !!(String(raw?.source ?? '').trim()
      || /^https?:\\/\\//i.test(String(raw?.source_url ?? '')));"""
NEW_BASIS = """    // ★★ 2026-10-20（真单 AD-20261020-006 那张卡）：「有依据」= **能解析出登记来源**，不是"字段非空"。
    //   病灶：原先只看 `String(source).trim()` 是否非空 ⇒ 提示词教的占位值 `source:"none"`
    //   也算「有依据」⇒ `basis_missing=false` ⇒ 展示层过滤器放行 ⇒ 卡面印出
    //   「依据：独立语义复核（非条款依据，需人工核对）」—— 而那句正是
    //   Owner 2026-10-19 明令不许出现的自我否定（判它在、又说它没依据）。
    //   判据与渲染侧**同一把尺**：`resolveSourceId()`（闭集 S1–S17，见 `ext_basis.mjs`）。
    //   URL 落在 `source` 里（模型写错格）⇒ 也算有依据，并在下面归一化进 `source_url`。
    const _srcRaw = String(raw?.source ?? '').trim();
    const _srcIsUrl = /^https?:\\/\\//i.test(_srcRaw);
    const _hasBasis = _srcIsUrl || !!resolveSourceId(_srcRaw)
      || /^https?:\\/\\//i.test(String(raw?.source_url ?? ''));"""

# ── ② model_side.mjs：URL 误写进 source ⇒ 归一化 ─────────────────────────────
OLD_SRCURL = """      source_url: sanitizeUrl(raw?.source_url),"""
NEW_SRCURL = """      source_url: sanitizeUrl(raw?.source_url) || (_srcIsUrl ? sanitizeUrl(_srcRaw) : null),"""

# ── ③ model_side.mjs：提示词不再教占位值 ─────────────────────────────────────
OLD_PROMPT = """  '   实在找不到依据，就写 `source:"none"`，并在 `reason` 里写清你**凭什么**这么判',
  '   （通用经验？平台惯例？），我会在卡片上如实标成「本条无外部来源」。',"""
NEW_PROMPT = """  '   实在找不到依据 ⇒ **这条不要报**（写 `source:"none"` 这类占位值同样会被判成"没依据"、',
  '   **不会**列到卡片上；与其留一条读者无法核对的"问题"，不如只报你**说得清凭什么**的那些）。',"""

# ── ④ test_agent.mjs：加一组判据（含反向对照）────────────────────────────────
ANCHOR_TEST = """await t('Z59 ★★ 卡面三处收口：链接只留一条（保留下面的）、原因不许是内部口径、修改建议 ≤30 字', async () => {"""

NEW_TEST = """await t('Z61 ★★ 「有依据」= 能解析出登记来源（占位词不算）；URL 写错格要归一化', async () => {
  // Owner 2026-10-20 拿真卡（AD-20261020-006）来问的那一单：两条都印着
  // 「依据：独立语义复核（非条款依据，需人工核对）」，而 2026-10-19 已明令不许这句出现。
  // 根因在解析边界：提示词教模型「找不到依据就写 source:"none"」，
  // 而 `_hasBasis` 只看「source 是不是非空字符串」⇒ 占位词也算有依据 ⇒ 放上卡。
  const M = await import('./agent/model_side.mjs');
  const T = await import('./agent/dual_track.mjs');
  const base = { location: '图 1 第 2 处', category: '品牌信任与声誉', severity: 'REVIEW',
                 reason: '美式英语无此搭配，美国消费者读不懂品牌主张',
                 suggestion: '改为通顺的英文标语' };

  // ① 占位值 / 不在闭集里的假 id ⇒ 必须判「没依据」，且**不上卡**（并如实说明滤掉了几条）
  for (const ph of ['none', 'null', 'n/a', 'S99']) {
    const p = M.parseFindings(JSON.stringify([{ ...base, source: ph }]));
    assert.strictEqual(p.findings[0] && p.findings[0].basis_missing, true,
      `source:"${ph}" 被当成了「有依据」—— 卡上会再印出那句「非条款依据」`);
    const card = T.renderMerged(T.mergeFindings([], p.findings).items,
      { state: 'REVIEW', reportUrlOverride: null });
    assert.ok(!/非条款依据/.test(String(card.block)),
      `source:"${ph}" 的条目仍上了卡（卡面印了「非条款依据」）`);
    assert.ok(/未给出依据/.test(String(card.block)), '滤掉之后没有如实说明（静默丢条目）');
  }

  // ② 真登记来源 ⇒ 有依据（别把正常条目一起判死）
  const okS = M.parseFindings(JSON.stringify([{ ...base, source: 'S14' }]));
  assert.strictEqual(okS.findings[0].basis_missing, false, '真登记来源 S14 被判成没依据');

  // ③ 闭集之外的公开规则 ⇒ 给 URL 就算有依据
  const okU = M.parseFindings(JSON.stringify([{ ...base,
    source_url: 'https://www.ftc.gov/business-guidance/resources/x', source_name: 'FTC' }]));
  assert.strictEqual(okU.findings[0].basis_missing, false, '给了可核 URL 却被判没依据');

  // ④ ★ 反向对照：URL 写错格（写进 `source`）⇒ 归一化到 `source_url`，不算发明、也不白丢
  const mis = M.parseFindings(JSON.stringify([{ ...base,
    source: 'https://www.ftc.gov/business-guidance/resources/y' }]));
  assert.strictEqual(mis.findings[0].basis_missing, false, 'URL 写进 source 被判成没依据（会白丢一条）');
  assert.ok(/ftc\\.gov/.test(String(mis.findings[0].source_url)), 'URL 写进 source 没被归一化');

  // ⑤ ★ 反向对照（安全方向）：缺 source 与 source_url **两者皆空** ⇒ 仍然判没依据
  const none = M.parseFindings(JSON.stringify([{ ...base }]));
  assert.strictEqual(none.findings[0].basis_missing, true, '两格都空却被判有依据（那是漏放方向）');
});

"""

PATCHES = [
    (MODEL_SIDE, "① 依据判定改用 resolveSourceId", OLD_BASIS, NEW_BASIS),
    (MODEL_SIDE, "② URL 写错格归一化", OLD_SRCURL, NEW_SRCURL),
    (MODEL_SIDE, "③ 提示词不再教占位值", OLD_PROMPT, NEW_PROMPT),
    (TEST_AGENT, "④ 补 Z61 判据（含反向对照）", ANCHOR_TEST, NEW_TEST + ANCHOR_TEST),
]


def sha8(p: str) -> str:
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:8]
    except Exception:
        return "absent"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真写（默认只预演）")
    a = ap.parse_args()

    print("守衡仓：%s（model_side sha8=%s ｜ test_agent sha8=%s）"
          % (SH_REPO, sha8(MODEL_SIDE), sha8(TEST_AGENT)))

    texts = {}
    for path, label, old, new in PATCHES:
        if path not in texts:
            if not os.path.exists(path):
                print("  ❌ %s 不在：%s" % (label, path))
                return 2
            texts[path] = open(path, encoding="utf-8").read()
        n = texts[path].count(old)
        state = "已打过" if (n == 0 and texts[path].count(new.split("\n")[2] if "\n" in new else new) > 0) else ("待打" if n == 1 else "⛔")
        print("  %-28s 命中 %d 次  %s" % (label, n, state))
        if n != 1:
            print("  ❌ 「%s」不是恰好一处（%d 次）—— 整体不落盘，避免半成品补丁" % (label, n))
            return 3
        texts[path] = texts[path].replace(old, new, 1)

    if not a.apply:
        print("预演通过（三道替换各命中一次）。要真写加 --apply。")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for path, body in texts.items():
        bak = "%s.bak-basis-%s" % (path, stamp)
        shutil.copy2(path, bak)
        tmp = path + ".tmp-basis"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        # 逐处校验：写完读回来，四处标志必须都在
        back = open(tmp, encoding="utf-8").read()
        for token in ("resolveSourceId(_srcRaw)", "_srcIsUrl ? sanitizeUrl(_srcRaw)",
                      "这条不要报", "Z61 ★★"):
            if path.endswith("test_agent.mjs") and token != "Z61 ★★":
                continue
            if path.endswith("model_side.mjs") and token == "Z61 ★★":
                continue
            if token not in back:
                print("  ❌ 读回校验失败：%s 缺 %s（原文件已备份 %s）" % (path, token, bak))
                os.unlink(tmp)
                return 4
        os.replace(tmp, path)
        print("  ✅ 已写 %s（备份 %s，新 sha8=%s）" % (path, os.path.basename(bak), sha8(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
