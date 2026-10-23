import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { SYSTEM as MODEL_SIDE_SYSTEM } from '../../tools/agent/model_side.mjs';
import { IMAGE_REVIEW_CACHE_VERSION } from '../../tools/agent/image_review_cache.mjs';

const sha = (v) => createHash('sha256').update(v).digest('hex');
const IMG = '75b5790174e153acd52bd910c1bdad46ddca7e33165a06d8324d5281cb3bb1a3';
const model = 'https://api.deepseek.com:deepseek-flash';
const keyOf = (contract) => sha(JSON.stringify({ version: IMAGE_REVIEW_CACHE_VERSION,
  images: [IMG], model, contract: sha(contract) }));

const nowKey = keyOf(`${MODEL_SIDE_SYSTEM}\nimage-safety-full-review-v1`);
const dump = JSON.parse(fs.readFileSync('PMO/shouheng-state/image-review-results.json', 'utf8'));
const entries = dump.entries;
console.log('当前代码算出的稳定键 =', nowKey.slice(0, 16), '| 缓存里有没有 =', nowKey in entries);
for (const [k, v] of Object.entries(entries)) {
  console.log(' ', k.slice(0, 16), 'findings', (v.findings || []).length, k === nowKey ? '← 当前政策键' : '');
}
