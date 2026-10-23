/**
 * Stable model-side result reuse for repeated reviews of the same image.
 *
 * Chat wording, mentions, OCR wrappers, and room identity must not produce a
 * different semantic review for identical source pixels. The cache is keyed
 * by ordered original-image digests plus the model and review contract. It
 * stores findings only; source image bytes and raw model responses never land
 * in the cache.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { stateDir } from './config.mjs';

export const IMAGE_REVIEW_CACHE_VERSION = 'image-review-findings-v1';
const MAX_ENTRIES = 256;
const inFlight = new Map();

const sha256 = (value) => createHash('sha256').update(value).digest('hex');

export function imageReviewCacheKey({ imagePaths = [], model = '', contract = '', cacheContract = contract } = {}) {
  const digests = [];
  try {
    for (const imagePath of imagePaths) {
      if (!imagePath) return null;
      const bytes = fs.readFileSync(imagePath);
      digests.push(sha256(bytes));
    }
  } catch {
    return null;
  }
  if (!digests.length) return null;
  return sha256(JSON.stringify({
    version: IMAGE_REVIEW_CACHE_VERSION,
    images: digests,
    model: String(model ?? ''),
    // `contract` may contain OCR/scene text that differs between transports.
    // `cacheContract` identifies the stable audit policy shared by DM and group.
    contract: sha256(String(cacheContract ?? '')),
  }));
}

function cacheFile(file) {
  return file || path.join(stateDir(), 'image-review-results.json');
}

function readCache(file) {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (parsed?.schema !== IMAGE_REVIEW_CACHE_VERSION || !parsed.entries
        || typeof parsed.entries !== 'object' || Array.isArray(parsed.entries)) return {};
    return parsed.entries;
  } catch {
    return {};
  }
}

function findingsOnly(result) {
  return {
    ok: true,
    findings: result.findings.map((f) => {
      const { url_probe, ...stable } = f ?? {};
      return stable;
    }),
    dropped: Array.isArray(result.dropped) ? result.dropped : [],
    ...(result.basis && typeof result.basis === 'object' ? { basis: result.basis } : {}),
  };
}

function writeCache(file, key, value) {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const entries = readCache(file);
    entries[key] = value;
    const kept = Object.fromEntries(Object.entries(entries).slice(-MAX_ENTRIES));
    const temp = `${file}.${process.pid}.${Date.now()}.tmp`;
    fs.writeFileSync(temp, JSON.stringify({ schema: IMAGE_REVIEW_CACHE_VERSION, entries: kept }));
    fs.renameSync(temp, file);
    return true;
  } catch (error) {
    console.warn(`[image-review-cache] cache write failed: ${error?.code ?? error?.message}`);
    return false;
  }
}

/**
 * Run a visual review once per exact image set and review contract.
 * `run` is called only on a miss. Failed/invalid responses are never cached.
 */
export async function reviewImageOnce({ imagePaths = [], model = '', contract = '', cacheContract = contract, run,
                                       file = null } = {}) {
  if (typeof run !== 'function') throw new TypeError('reviewImageOnce requires run()');
  const key = imageReviewCacheKey({ imagePaths, model, contract, cacheContract });
  if (!key) return run();
  const target = cacheFile(file);
  const entries = readCache(target);
  const hit = entries[key];
  if (hit?.ok === true && Array.isArray(hit.findings)) {
    console.log(`[image-review-cache] image findings reused (key=${key.slice(0, 12)})`);
    return { ...hit, ms: 0, cached: true };
  }
  const flightKey = `${target}\n${key}`;
  if (inFlight.has(flightKey)) {
    const shared = await inFlight.get(flightKey);
    return shared?.ok === true
      ? { ...shared, ms: 0, cached: true }
      : shared;
  }
  const pending = (async () => {
    const result = await run();
    if (result?.ok === true && Array.isArray(result.findings)) {
      const stored = findingsOnly(result);
      writeCache(target, key, stored);
      return { ...stored, ...(Number.isFinite(result.ms) ? { ms: result.ms } : {}) };
    }
    return result;
  })();
  inFlight.set(flightKey, pending);
  try { return await pending; }
  finally { inFlight.delete(flightKey); }
}
