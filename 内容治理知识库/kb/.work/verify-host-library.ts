/**
 * 派生宿主库的自检（用工作台**自己的**解析器验，不另写一套 YAML 解析）。
 *
 * 为什么复用工作台的 `frontmatter.ts`：宿主库最终是喂给工作台镜像器的，判据以它为准。
 * 自己写一遍解析器、「我这版能读」不构成证据 —— 要验的是**它**能不能读。
 *
 * 跑法（没有 node 在 PATH，用 DSH 自带的垫片）：
 *   cd 工作台 && ./scripts/node-env.sh "/abs/path/to/kb/.work/verify-host-library.ts" --root "/abs/path/to/hostlib"
 *
 * 检查项：
 *   1. 每个条目 frontmatter 解析无 error，且必填字段齐全（id/collection/tier/topic/summary/owner/
 *      evidence_level/data_level/half_life_days/created_at/valid_until/asks/not_proves/source）
 *   2. id 全局唯一；id 与文件名一致
 *   3. collection 字段 == 它所在的顶层子库目录名（宿主库 E017 这条纪律）
 *   4. tier ∈ 镜像器认的五个层目录，且 == 所在层目录名
 *   5. valid_until == created_at + half_life_days
 *   6. `_meta/collections.yaml` 能登记上每个子库，且 entry_count 与磁盘实际条数一致
 *      （对不上会被工作台的 drift 检测抓出来 —— 这里先自曝）
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, basename } from 'node:path';
import { parseEntry } from '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/工作台/apps/server/src/kb/frontmatter.ts';
import { parseCollectionsRegistry } from '/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/工作台/apps/server/src/kb/kb-collections-registry.ts';

const TIERS = ['L0-raw', 'L1-facts', 'L2-concepts', 'L3-graph', 'L4-contracts'];
const REQUIRED = [
  'id', 'title', 'collection', 'tier', 'topic', 'summary', 'owner',
  'evidence_level', 'data_level', 'half_life_days', 'created_at', 'valid_until',
  'asks', 'not_proves', 'source',
];

function arg(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

const root = arg('--root');
if (root === undefined) {
  console.error('用法：verify-host-library.ts --root <宿主库根>');
  process.exit(2);
}

const problems: string[] = [];
const ids = new Map<string, string>();
const perCollection = new Map<string, number>();
let docs = 0;
let badFrontmatter = 0;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    if (name.startsWith('.')) continue;
    const abs = join(dir, name);
    if (statSync(abs).isDirectory()) out.push(...walk(abs));
    else if (name.endsWith('.md')) out.push(abs);
  }
  return out;
}

for (const abs of walk(root)) {
  const rel = relative(root, abs);
  const segments = rel.split('/');
  if (segments[0] === '_meta') continue;
  if (segments.length !== 3) {
    problems.push(`${rel}：不在 <子库>/<层目录>/<id>.md 这个形状里（镜像器不认）`);
    continue;
  }
  const [collectionDir, tierDir] = segments as [string, string, string];
  docs += 1;
  perCollection.set(collectionDir, (perCollection.get(collectionDir) ?? 0) + 1);

  const text = readFileSync(abs, 'utf8');
  const { meta, error, rawMeta } = parseEntry(text);
  if (error !== undefined) {
    problems.push(`${rel}：frontmatter 解析失败 —— ${error}`);
    badFrontmatter += 1;
    continue;
  }
  if (rawMeta === undefined) {
    problems.push(`${rel}：没有 frontmatter`);
    badFrontmatter += 1;
    continue;
  }
  for (const field of REQUIRED) {
    const value = rawMeta[field];
    if (value === undefined || value === null || value === '') {
      problems.push(`${rel}：缺必填字段 ${field}`);
    }
  }
  if (meta.entryId === undefined) problems.push(`${rel}：id 读不出来`);
  else {
    const expected = basename(abs, '.md');
    if (meta.entryId !== expected) problems.push(`${rel}：id（${meta.entryId}）与文件名不一致`);
    const previous = ids.get(meta.entryId);
    if (previous !== undefined) problems.push(`${rel}：id 与 ${previous} 重复`);
    ids.set(meta.entryId, rel);
  }
  if (meta.collection !== collectionDir) {
    problems.push(`${rel}：collection（${meta.collection}）≠ 所在子库目录（${collectionDir}）`);
  }
  if (meta.tier !== tierDir) problems.push(`${rel}：tier（${meta.tier}）≠ 所在层目录（${tierDir}）`);
  if (meta.tier !== undefined && !TIERS.includes(meta.tier)) {
    problems.push(`${rel}：tier（${meta.tier}）不在镜像器认的五个层目录里`);
  }
  if (meta.asks.length === 0) problems.push(`${rel}：asks 为空`);
  if (meta.halfLifeDays !== undefined && meta.createdAt !== undefined && meta.validUntil !== undefined) {
    const created = new Date(`${meta.createdAt}T00:00:00Z`);
    const expected = new Date(created.getTime() + meta.halfLifeDays * 86_400_000).toISOString().slice(0, 10);
    if (expected !== meta.validUntil) {
      problems.push(`${rel}：valid_until（${meta.validUntil}）≠ created_at + half_life_days（${expected}）`);
    }
  }
  if (meta.notProves === undefined || meta.notProves.trim() === '') {
    problems.push(`${rel}：not_proves 为空（边界声明不许丢）`);
  }
}

// 登记表对账
const registryPath = join(root, '_meta', 'collections.yaml');
const registry = parseCollectionsRegistry(readFileSync(registryPath, 'utf8'));
if (registry.error !== undefined) problems.push(`collections.yaml 解析失败：${registry.error}`);
const registered = new Map(registry.collections.map((item) => [item.id, item]));
for (const [dir, count] of perCollection) {
  const item = registered.get(dir);
  if (item === undefined) {
    problems.push(`子库「${dir}」有 ${count} 条但没在 _meta/collections.yaml 登记`);
    continue;
  }
  if (item.entryCount !== count) {
    problems.push(`子库「${dir}」登记 entry_count=${item.entryCount}，磁盘实际 ${count}（会被工作台判成漂移）`);
  }
  if (item.owner === undefined || item.owner.trim() === '') problems.push(`子库「${dir}」登记表 owner 为空`);
}
for (const [dir] of registered) {
  if (!perCollection.has(dir)) problems.push(`子库「${dir}」登记了但盘上没有条目（镜像器会跳过空库）`);
}

console.log(`[verify] 根：${root}`);
console.log(`[verify] 条目 ${docs} 条；frontmatter 坏 ${badFrontmatter} 条；子库 ${perCollection.size} 个`);
for (const [dir, count] of [...perCollection].sort()) console.log(`[verify]   ${dir}: ${count}`);
if (problems.length === 0) {
  console.log('[verify] PASS：没有发现问题');
  process.exit(0);
}
console.log(`[verify] FAIL：${problems.length} 个问题`);
for (const item of problems.slice(0, 40)) console.log(`  · ${item}`);
if (problems.length > 40) console.log(`  · …另有 ${problems.length - 40} 条`);
process.exit(1);
