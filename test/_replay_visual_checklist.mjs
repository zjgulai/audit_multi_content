#!/usr/bin/env node
/**
 * 用**生产原文**回放视觉核对判据（2026-10-22 19:36 那一单）。
 *
 *   node test/_replay_visual_checklist.mjs
 *
 * 三条读数：
 *   ① 真实链回答（`kb/.work/last_chain_answer.txt`，当时被判「场景关系 判未测但没给原因」的原文）
 *      ⇒ 现在必须 ok=true（它是「同上」指代，理由在上一行）；
 *   ② 把「同上」上面那条理由删掉 ⇒ 必须重新变红（判据没被改松）；
 *   ③ 结论不同却写「同上」⇒ 必须红（跨结论的同上不许继承）。
 */
import fs from 'node:fs';
import assert from 'node:assert';
import { checkVisualChecklist, checkImageSkillWorkflow } from '../tools/agent/visual_checklist.mjs';

const FILE = '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/.work/last_chain_answer.txt';
const raw = fs.readFileSync(FILE, 'utf8');
// 去掉前两行机器抬头（`# at=…` / `# base=…`），它们不是报告正文
// ⚠️ 别用 /^#[^\n]*$/ 一刀切 —— 那会把 `## 1. 审核对象与范围` 这些**章节标题**一起删掉
const answer = raw.replace(/^# (?:at|base)=[^\n]*\n/gm, '');

const visual = checkVisualChecklist(answer);
const workflow = checkImageSkillWorkflow(answer);

console.log('① 生产原文回放');
console.log(`   视觉核对 ok=${visual.ok}｜reason=${visual.reason || '（无）'}`);
console.log(`   skill 全流程 ok=${workflow.ok}｜reason=${workflow.reason || '（无）'}`);
console.log(`   场景关系：verdict=${visual.found.scene_relation?.verdict}`
  + `｜basis=${JSON.stringify(visual.found.scene_relation?.basis)}`
  + `｜继承自=${visual.found.scene_relation?.inheritedFrom ?? '（无）'}`);
assert.strictEqual(visual.ok, true, '真实报告仍被判红 —— 修没修好');
assert.strictEqual(workflow.ok, true, 'skill 全流程仍被判红');
assert.strictEqual(visual.found.scene_relation?.verdict, '未测');

console.log('\n② 反向对照：抽掉「同上」上面那条原因 ⇒ 必须重新红');
const noReason = answer.replace('| 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |',
  '| 产品状态 | **未测** |  |');
const red = checkVisualChecklist(noReason);
console.log(`   ok=${red.ok}｜reason=${red.reason}`);
assert.strictEqual(red.ok, false, '上一条没原因了，「同上」还被放过 —— 判据被改松了');

console.log('\n③ 反向对照：结论不同却写「同上」⇒ 必须红');
const mismatch = answer.replace('| 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |',
  '| 产品状态 | **有** | 画面里床头柜上放着倒置的奶瓶 |');
const miss = checkVisualChecklist(mismatch);
console.log(`   ok=${miss.ok}｜reason=${miss.reason}`);
assert.strictEqual(miss.ok, false, '跨结论的「同上」被当成继承 —— 判据太松');

console.log('\n④ 反向对照：只有一句「同上」、前面没有可用原因 ⇒ 必须红');
const onlySame = '婴幼儿姿势=未测；婴儿睡眠位置=未测；产品状态=未测；场景关系=未测；隐私=未测';
const bare = checkVisualChecklist(onlySame);
console.log(`   ok=${bare.ok}｜reason=${bare.reason}`);
assert.strictEqual(bare.ok, false, '五类都只写「未测」不给原因也被放过');

console.log('\n✅ 回放 4 组全过');
