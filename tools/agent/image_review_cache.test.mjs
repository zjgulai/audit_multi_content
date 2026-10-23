import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { imageReviewCacheKey, reviewImageOnce } from './image_review_cache.mjs';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sh-image-review-cache-'));
const image = path.join(dir, 'source.png');
const cache = path.join(dir, 'state', 'cache.json');
fs.writeFileSync(image, Buffer.from([0, 1, 2, 3, 4]));

const base = { imagePaths: [image], model: 'provider:model-v1', contract: 'full image audit v1' };
const key = imageReviewCacheKey(base);
assert.ok(key, 'original image digest should produce a cache key');
assert.notEqual(imageReviewCacheKey({ ...base, model: 'provider:model-v2' }), key,
  'model change must invalidate the cached result');
assert.notEqual(imageReviewCacheKey({ ...base, contract: 'full image audit v2' }), key,
  'review contract change must invalidate the cached result');
assert.equal(imageReviewCacheKey({ ...base, contract: 'different OCR/scene readout',
  cacheContract: base.contract }), key,
  'variable OCR/scene text must not split entries under the same stable policy');
assert.notEqual(imageReviewCacheKey({ ...base, cacheContract: 'image audit policy v2' }), key,
  'a deliberate stable-policy change must invalidate the cached result');

let calls = 0;
const finding = { location: '图 1 第 2 处', reason: '可见信息与表达不一致', suggestion: '修正文案' };
const run = async () => { calls++; return { ok: true, findings: [finding], dropped: [], ms: 30, raw: 'do not persist' }; };
const first = await reviewImageOnce({ ...base, file: cache, run });
assert.equal(calls, 1, 'first identical-image audit should run model');
assert.deepEqual(first.findings, [finding]);

// Channel, mention, and generic chat question are intentionally not part of
// the key: both DM and group image audits resolve to the exact same record.
const second = await reviewImageOnce({ ...base, file: cache, run: async () => {
  calls++;
  return { ok: true, findings: [], dropped: [], ms: 10 };
} });
assert.equal(calls, 1, 'same image and contract must reuse across chat sessions');
assert.equal(second.cached, true);
assert.deepEqual(second.findings, [finding]);
assert.equal(second.ms, 0);
const changedReadout = await reviewImageOnce({ ...base, file: cache,
  contract: 'same image audit with truncated visual readout', cacheContract: base.contract,
  run: async () => { calls++; return { ok: true, findings: [], dropped: [], ms: 10 }; } });
assert.equal(calls, 1, 'a different per-session readout must reuse the same original-image result');
assert.equal(changedReadout.cached, true);
assert.deepEqual(changedReadout.findings, [finding]);
const disk = fs.readFileSync(cache, 'utf8');
assert.ok(!disk.includes('do not persist'), 'raw model response must not be persisted');

const failedCache = path.join(dir, 'state', 'failed.json');
let failedCalls = 0;
const failedRun = async () => { failedCalls++; return { ok: false, findings: [], error: 'fixture' }; };
const failure1 = await reviewImageOnce({ ...base, file: failedCache, run: failedRun });
const failure2 = await reviewImageOnce({ ...base, file: failedCache, run: failedRun });
assert.equal(failure1.ok, false);
assert.equal(failure2.ok, false);
assert.equal(failedCalls, 2, 'failed results must not be cached');

const concurrentCache = path.join(dir, 'state', 'concurrent.json');
let concurrentCalls = 0;
const delayed = () => new Promise((resolve) => setTimeout(() => {
  concurrentCalls++;
  resolve({ ok: true, findings: [finding], dropped: [] });
}, 10));
await Promise.all([
  reviewImageOnce({ ...base, file: concurrentCache, run: delayed }),
  reviewImageOnce({ ...base, file: concurrentCache, run: delayed }),
]);
assert.equal(concurrentCalls, 1, 'overlapping identical image audits must single-flight');

fs.rmSync(dir, { recursive: true, force: true });
console.log('image_review_cache.test: 14/14');
