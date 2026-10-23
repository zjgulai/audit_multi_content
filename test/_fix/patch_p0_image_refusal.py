#!/usr/bin/env python3
"""修：P0 确定性命中 + 带图单 ⇒ 图单两道闸门把 BLOCK 藏成「证据未通过」拒答。

病灶（生产实测，om_x100b62aff6a2c22ccfd45eeca787bff，2026-10-22 15:30）：
  刘华丽 发了一张 momcozy 产品图 ＋ @守衡（正文为空）。
  库侧 P0 快路命中 V02 / E-2.124 ⇒ dual.rendered 里 BLOCK 已经备好；
  随后 `imageEvidenceFailure` 判「本轮没有可核对的知识库引擎 JSON」，
  图单两道闸门（五类视觉核对 / skill 全流程）也在 P0 的 answer 上找它们要的节，
  而 PRD §6.3 明写「P0 命中即停止后续审查」—— 那两样**按设计就不该存在**。
  ⇒ 表落 NEEDS_INPUT、群里只收到「本轮图片审查证据未通过……请重新发送原图」。

修法两处（判据与闸门各一处，缺一处另一个方向就还漏）：
  ① imageEvidenceFailure：P0 快路读数在 ⇒ 不适用（P0 只出 BLOCK，不可能放行）；
  ② runSubmissionGate 的图单闸门块：P0 快路读数在 ⇒ 不跑（并留一行日志说明为什么跳过）。

用法：python3 test/_fix/patch_p0_image_refusal.py [--check]
"""
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
AGENT = os.path.join(ROOT, 'tools/agent/agent.mjs')
TEST = os.path.join(ROOT, 'tools/test_agent.mjs')
BACKUP = os.path.join(ROOT, 'test/_fix/backup_p0image')

A_OLD = """/** Require positive, current KB evidence before any image review state can be published. */
export function imageEvidenceFailure(result, imageCount = 0, modelSide = null) {
  if (!(Number(imageCount) > 0)) return null;
  if (!modelSide || modelSide.ok !== true || modelSide.skipped) {"""

A_NEW = """/** Require positive, current KB evidence before any image review state can be published. */
export function imageEvidenceFailure(result, imageCount = 0, modelSide = null) {
  if (!(Number(imageCount) > 0)) return null;
  // ★★ 2026-10-22（Owner 现场那一单：图 + @守衡）—— **P0 确定性命中时这道闸不适用。**
  //
  //   病灶（生产实测，`om_x100b62aff6a2c22ccfd45eeca787bff`）：刘华丽 发了一张 momcozy 产品图
  //   ＋ @守衡（正文为空）。库侧 P0 快路命中 V02／E-2.124，`dual.rendered` 里 BLOCK 已经备好，
  //   而本函数却判「本轮没有可核对的知识库引擎 JSON」⇒ 强制 NEEDS_INPUT ⇒ 群里只收到
  //   一句「本轮图片审查证据未通过……请重新发送原图」。**一个已确定的 BLOCK 被自己的闸门藏掉。**
  //   为什么是判据本身错、而不是读数缺：
  //     ① 这一路**按设计就不会有**引擎 JSON —— PRD §6.3「P0 命中即停止后续审查」，
  //        L4→L7 与评审链根本没跑；拿一份「按 PRD 不该存在」的产物当缺证据，
  //        等于让每张命中 P0 的图单都必然拒答（§2.4.5 那种「两个各自都对的部件撞车」）。
  //     ② P0 的读数**自带**条款号 / 锚点 / source_sha256 / 报告链接，且只出 BLOCK ——
  //        这道闸防的是「没读过库就说合规（PASS）」，P0 只可能更保守，不存在那个风险。
  if (result?.p0_fastpath && typeof result.p0_fastpath === 'object') return null;
  if (!modelSide || modelSide.ok !== true || modelSide.skipped) {"""

B_OLD = """    if ((inbound?.imageCount ?? 0) > 0 && chainRan) {
      // ★ 2026-10-21：把「读数里有姿态异常的容器」一路喂给判据 —— 只看「有没有写四类」不够：
      //   模型可以照着读数交一份格式齐全的清单，而读数里那个倒着的瓶子一个字不提。"""

B_NEW = """    // ★★ 2026-10-22（Owner 现场那一单：图 + @守衡）—— **P0 确定性命中 ⇒ 图单两道闸门不适用。**
    //   同一单实测（`om_x100b62aff6a2c22ccfd45eeca787bff`）：库侧 P0 快路 BLOCK（V02／E-2.124）
    //   与模型侧 2 条合并成 BLOCK、`p0DirectReply` 已备好；而这两道闸门去 P0 的 `answer` 里找
    //   五类视觉核对与 skill 全流程节 —— 按 PRD §6.3「命中即停止后续审查」，判定主体根本没被调，
    //   那些节**按设计就不会有** ⇒ 必然缺项 ⇒ 强制 NEEDS_INPUT + 回「证据未通过」拒答：
    //   **一个已确定的 BLOCK 被自己的闸门藏掉，群里什么三态结论都没有**（§2.4.5 接缝撞车）。
    //   边界（一个字不松）：只对 `p0_fastpath` 命中生效；P0 只出 BLOCK，
    //   不存在它把「视觉没核对」的地方放行出去的可能。
    const p0GateExempt = res?.p0_fastpath && typeof res.p0_fastpath === 'object';
    if ((inbound?.imageCount ?? 0) > 0 && chainRan && !p0GateExempt) {
      // ★ 2026-10-21：把「读数里有姿态异常的容器」一路喂给判据 —— 只看「有没有写四类」不够：
      //   模型可以照着读数交一份格式齐全的清单，而读数里那个倒着的瓶子一个字不提。"""

C_MARK = """});

await t('Z45 ★★ P0 命中 ⇒ 置信度**两侧同档 1.0**"""

C_NEW = """});

await t('N4e ★★ P0 确定性命中＋带图 ⇒ 图单两道闸门不适用，BLOCK 必须照发（Owner 2026-10-22 那张被拒答的图）', async () => {
  // ── 病灶（生产实测，`om_x100b62aff6a2c22ccfd45eeca787bff`，2026-10-22 15:30）
  //   刘华丽 发了一张 momcozy 产品图 ＋ @守衡（正文为空，只有 OCR 与画面读数）。
  //   库侧 P0 快路命中 V02／E-2.124 ⇒ 双轨合并态 BLOCK、`p0DirectReply` 已备好；
  //   而 `imageEvidenceFailure`（要引擎 JSON）＋ 图单两道闸门（要五类视觉核对、skill 全流程节）
  //   都挂在**只有模型侧才产出**的东西上，而 PRD §6.3 说 P0 命中即停后续审查、模型侧不该跑。
  //   ⇒ 必然缺项 ⇒ 表里落 NEEDS_INPUT、群里收到「本轮图片审查证据未通过……请重新发送原图」，
  //   **BLOCK 被自己的闸门藏掉**（§2.4.5 的接缝撞车）。
  //   本组钉两件：① P0＋图 ⇒ 不拒答、结论仍是 BLOCK、§5.3 结论行在；
  //              ② 反向对照：把 P0 摘掉，同一张图**必须**仍被拒（否则就是「把闸门整个关掉」）。
  const { runSubmissionGate, imageEvidenceFailure, finalVerdict53ForTurn } = await import('./agent/agent.mjs');
  const P0_RENDERED = '【审查结论：BLOCK】共发现 1 处必须修改。\\n逐条问题\\n· 绝对化用语（E-2.124）：「100%」无证据支撑。';
  const P0_CHAIN = {
    ok: true,
    answer: P0_RENDERED,
    p0_fastpath: { mode: 'p0_fastpath', elapsed_ms: 115, matched_patterns: 1, rule_codes: ['V02'],
                   layer_preflight: { mode: 'p0_fastpath', enforced: false, is_pass_basis: false } },
    p0_findings: [{ rule_code: 'V02', level: 'P0', verdict: 'BLOCK', article_no: 'E-2.124',
                    matched: [{ line_text: '100%', span: [0, 4] }], matched_count: 1 }],
    advisories: [], issue_count: 1, confidence: 1.0,
    report: 'https://example.invalid/docx/P0STUB', report_path: null, report_detail: '自证桩',
    product_line: '', channel: '',
  };
  const imgInbound = { text: '', imageCount: 1, videoCount: 0,
                       images: [{ index: 1, wlText: 'Nipple Cream 100%', lines: 17 }] };
  const modelFindings = [{
    location: '图 1 主视觉', category: '推广与价格透明', severity: 'REVIEW',
    reason: '组合价适用范围含糊', excerpt: 'Choose Any 3 Pay Less than $99',
    suggestion: '写明适用品类', source: 'none',
  }];
  const runWith = async (chainRes) => {
    let row = null;
    const result = await runSubmissionGate({
      inbound: imgInbound, question: imgInbound.text, notify: async () => {},
      chainRunner: async () => chainRes,
      modelSideRunner: async () => ({ ok: true, findings: modelFindings, dropped: [] }),
      publishRunner: async (r) => { row = r; return { ok: true, action: 'skipped', detail: '自证桩' }; },
      mergedReportRunner: async () => ({ ok: true, url: 'https://example.invalid/docx/STUB', detail: '自证桩' }),
      adviceRunner: async () => ({ ok: true, ms: 1, advice: {} }),
      mediaLinksRunner: async () => [],
      mediaUpload: async () => ({ ok: false, reason: '自证桩：不真上传' }),
      fetchImageForLink: async () => null,
      fetchVideoForLink: async () => null,
    });
    return { row, result };
  };

  // ① 正向：P0 命中 ⇒ 不拒答、结论 BLOCK、§5.3 结论行在
  const hit = await runWith(P0_CHAIN);
  assert.ok(hit.row, 'P0＋图单没有落表（连留痕都没有）');
  assert.strictEqual(hit.row.conclusion, 'BLOCK',
    `P0 命中的图单被压成了 ${hit.row.conclusion} —— 已确定的 BLOCK 被图单闸门藏掉`);
  assert.strictEqual(hit.result.forcedReply, null,
    'P0 确定性命中的图单仍被强制替换成「证据未通过」拒答话术');
  assert.strictEqual(hit.result.imageReviewIncomplete, false,
    'P0 命中的图单被标成「图片审查未完成」，下游据此丢掉整份结论');
  assert.ok(String(hit.result.verdict53?.line ?? '').includes('BLOCK'),
    `P0＋图单拿不到 §5.3 结论行：${JSON.stringify(hit.result.verdict53)}`);
  assert.ok(finalVerdict53ForTurn({ gateResult: hit.result }),
    'P0＋图单的最终结论行被 imageReviewIncomplete 抹掉');
  assert.ok(String(hit.result.p0DirectReply ?? '').includes('【审查结论：BLOCK】'),
    'P0 直达回复不是那张 BLOCK 卡（群里会没有三态结论）');
  // ② 判据本身：P0 读数在 ⇒ 不需要引擎 JSON；模型侧整轮没跑也不拦（PRD §6.3 主动停审）
  assert.strictEqual(imageEvidenceFailure(P0_CHAIN, 1, { ok: true, findings: [] }), null,
    'P0 命中仍被要「知识库引擎 JSON」—— P0 快路按 PRD §6.3 根本不跑那一段');
  assert.strictEqual(imageEvidenceFailure(P0_CHAIN, 1, { ok: false, error: '自证桩：模型侧未跑' }), null,
    'P0 命中的图单仍被要「模型侧原图审查」—— 而命中即停，模型侧本来就不该跑');
  // ③ 反向对照：摘掉 P0 读数（同一张图、同一份模型侧）⇒ 仍必须拒（闸门没被整体关掉）
  const plain = await runWith({ ok: true,
    answer: '【审查结论：REVIEW】共发现 1 处需人工确认。\\n逐条问题\\n· 价格表述含糊' });
  assert.strictEqual(plain.row?.conclusion, 'NEEDS_INPUT',
    `没有 P0 的图单缺视觉核对 / 引擎读数时落了 ${plain.row?.conclusion} —— 闸门被改松了`);
  assert.ok(String(plain.result.forcedReply ?? '').includes('暂不出 PASS / REVIEW / BLOCK'),
    '没有 P0 的图单缺项时不再强制拒收');
  assert.ok(imageEvidenceFailure({ ok: true, answer: 'x' }, 1, { ok: true, findings: [] }),
    '没有 P0 读数、也没有引擎 JSON 的图单被当成证据齐全');
  // ④ 边界：这条闸本来就只管图单 —— imageCount=0 时连 P0 都不必看
  assert.strictEqual(imageEvidenceFailure(P0_CHAIN, 0, null), null,
    '文字单被这条闸门越界拦截');
});

await t('Z45 ★★ P0 命中 ⇒ 置信度**两侧同档 1.0**"""


def patch(src, old, new, label):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f'{label}：期望命中 1 处，实际 {n} 处 —— 源码已变，先读再改')
    return src.replace(old, new, 1)


def main():
    check = '--check' in sys.argv
    for p in (AGENT, TEST):
        if not os.path.exists(p):
            raise SystemExit(f'找不到 {p}')
    agent = open(AGENT, encoding='utf-8').read()
    test = open(TEST, encoding='utf-8').read()
    if 'p0GateExempt' in agent or 'N4e ★★ P0 确定性命中＋带图' in test:
        print('已经打过（幂等跳过）')
        return 0
    agent2 = patch(agent, A_OLD, A_NEW, 'agent.mjs · imageEvidenceFailure')
    agent2 = patch(agent2, B_OLD, B_NEW, 'agent.mjs · 图单闸门块')
    test2 = patch(test, C_MARK, C_NEW, 'test_agent.mjs · 插入 N4e')
    if check:
        print('--check：两处都能打上去（未落盘）')
        return 0
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(AGENT, os.path.join(BACKUP, 'agent.mjs.orig'))
    shutil.copy2(TEST, os.path.join(BACKUP, 'test_agent.mjs.orig'))
    open(AGENT, 'w', encoding='utf-8').write(agent2)
    open(TEST, 'w', encoding='utf-8').write(test2)
    print(f'✓ 已写入 {AGENT}')
    print(f'✓ 已写入 {TEST}')
    print(f'  备份在 {BACKUP}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
