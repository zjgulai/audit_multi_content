/**
 * ocr_watermark.mjs —— 把 **OCR 读到的水印**从"素材内容"里摘出去。
 *
 * ══════════════════════════════════════════════════════════════════════════
 * ★★ 2026-10-09（Owner 亲自看出来的，一句话点到根上）
 *
 *   Owner 原话：「图上文字：5615 RO0 刘华丽 刘华問 ==》**这是我，是因为图片上有水印吗？**」
 *
 *   他判断对。实测那张图的 OCR 全文（库内留痕，逐字）：
 *       5615 RO0 / 刘华丽 / 刘华問        ← 水印（用户名 + 工号）
 *       #MomAndMore activity calendar     ← 真内容从这里才开始
 *       Each Group has its own activities—choose the ones you like and join in.
 *       Every week： / 1topic activity & i+ comment or game
 *       Sep 15 / Mystery / activity / begins / 5 / 刘华問 / Week2 / Sep8-14 / 5615 RC
 *       Week1 / Sep 1-7 / 5615 ROOT / Week4 / Sep 22-28 / 5615 / 刘华 / Week3 …
 *       Winners / announcements / every weekend / 华 / 八613 / MOMCOZY / 1化司 / 5615
 *
 *   ── 为什么这一条是**根**，不是"显示不好看" ────────────────────────────────
 *   水印被当成素材内容 ⇒ 它**进了检索**（`review_gate.chainInput` 把 OCR 原文直接喂给链）
 *   ⇒ 拿「刘华丽 / 图片 / 文案」这类**水印里的常用词**去撞库（实测 BM25 207–210）
 *   ⇒ 撞出一堆**无关的内部样本**（实测撞到的是「设计美感」「亚马逊多语言修改」的评审记录）
 *   ⇒ 那几条又被渲染成「**命中**」进报告 ⇒ 整份报告的"问题"全是幻觉。
 *   一句话：**水印污染了检索输入**，后面再怎么修渲染都是白修。
 *
 *   ── 判据：**主判据用坐标**（2026-10-09 当天补上）────────────────────────────
 *   水印最可靠的特征不是"字面重复"，而是「**同一串出现在图的不同位置**」——
 *   文档水印就是同一个串被平铺到页面上。而 OCR 二进制本来就在输出每行的归一化坐标
 *   （`{t,c,x,y,w,h}`），只是上游 `vision.mjs::normalize()` 原先把它丢了
 *   （**已修**：现在带出 `boxes: [{t,x,y}]`）。
 *
 *   ⚠️ 为什么**不用** token 频率：实测过，它分不开 ——
 *     `Week1 / Week2 / Week3 / Week4` 与 `Sep 1-7 / Sep 8-14` 都会被算成"高频"，
 *     而它们是**真内容**（活动日历的周次）。误删真内容的代价是「素材被删了、结论会漏」，
 *     比漏判一个水印严重得多。⇒ 只认「**不同位置上的同一串（或近似同一串）**」。
 *
 *   ⚠️ **原始文本一个字都不丢**：`kept`/`dropped` 两侧都返回，调用方照旧把
 *      `text`（原文）给卡片显示 —— 人看得到"我读到了什么"，也看得到"其中哪些我判成水印"。
 *      库规：「搬是搬，砍是砍」；这里只是**换一份给检索用**。
 */

/** 一行（去空白后）不超过它，才**可能**是水印 —— 人名 / 工号 / 编号都是短串。 */
export const MAX_TOKEN_LEN = 24;
/** 两个位置的归一化距离小于它 ⇒ 视为**同一处**（水印是散开的，同处重复不算）。 */
export const MIN_POS_DIST = 0.15;

/**
 * 这一行像不像**真内容**？像就**绝不判水印**（误删代价不对称，见文件头）。
 *
 * 放行四类：
 *   · 过长（> MAX_TOKEN_LEN）；
 *   · 含中文句读或 markdown 痕迹（水印不会带标点）；
 *   · 含 URL / 邮箱 / 话题标签（#xxx）—— 那是内容；
 *   · 含 `let's` / `single-layer` 这类英文短语，或多词短句（≥4 个词）。
 */
export function looksLikeContent(line) {
  const raw = String(line ?? '').trim();
  if (!raw) return false;
  if (raw.length > MAX_TOKEN_LEN) return true;
  if (/[，。！？；：、（）「」【】《》]/.test(raw)) return true;
  if (/https?:\/\/|@[\w.-]+\.\w|#[\w\u4e00-\u9fa5]/.test(raw)) return true;
  if (/[A-Za-z]{3,}['-][A-Za-z]{2,}/.test(raw)) return true;
  if (raw.split(/\s+/).filter(Boolean).length >= 4) return true;
  return false;
}

/** 两个归一化坐标是不是**不同位置**。任一坐标缺失 ⇒ 判不了，返回 false（保守）。 */
function farApart(a, b) {
  if (![a?.x, a?.y, b?.x, b?.y].every((v) => Number.isFinite(v))) return false;
  return Math.abs(a.x - b.x) >= MIN_POS_DIST || Math.abs(a.y - b.y) >= MIN_POS_DIST;
}

/**
 * 从 OCR 结果里摘出水印行。
 *
 * ⚠️ **只有两条判据，都是"宁可漏、不可误删"**（见文件头那条不对称）：
 *   ① 有坐标时：**同一串出现在图的不同位置**（水印平铺的定义）；
 *   ② 没坐标时：同一串**字面重复 ≥2 次**。
 *
 * ⚠️ 实测**否掉**了"近似变体"判据（`5615 RO0` / `5615 R00` / `5615 RC`）：
 *   它会把 `Sep 15` / `Week1` / `Week2` / `Week3` / `Week4` / `Sep 1-7` 一起当水印删掉
 *   —— 而那些是**活动日历的真内容**（实测：35 行里误删 17 行，其中 8 行是内容）。
 *   代价不对称：**漏一个水印**只是检索里多几个噪声词；
 *   **误删一段真内容**是"素材被删了、结论会漏、而且看不出来"。
 *   ⇒ 变体水印（`5615 Rxx`）目前**只被部分覆盖**，剩下的**照实留在文本里**，
 *     由人去复核；**不拿一条会误伤的判据去换好看的数字**。
 *
 * @param {{text?:string, boxes?:Array<{t:string,x:number,y:number}>}} ocr
 *        `vision.ocrImage()` 的返回（`boxes` 是 2026-10-09 新加的）。
 * @returns {{text:string, kept:string[], dropped:string[], basis:string, droppedRatio:number}}
 *          `text` = **过滤后**（给检索用）；`basis` 说明这次靠哪条判据（可核）。
 */
export function stripOcrWatermark(ocr) {
  const src = typeof ocr === 'string' ? { text: ocr } : (ocr ?? {});
  const text = String(src.text ?? '');
  const lines = text.split('\n');
  const boxes = Array.isArray(src.boxes) ? src.boxes : [];

  const droppedIdx = new Set();
  let basis = 'none';

  // ⚠️ 必须**按下标配对**，不能按文本查（第一版就是按文本建 Map 查坐标 ⇒
  //    同一串的两次出现被压成一个 ⇒ `farApart` 恒 false ⇒ 一条水印都抓不到）。
  const candidates = lines
    .map((l, i) => ({ l, i, b: boxes[i] ?? null }))
    .filter((c) => c.l.trim() && !looksLikeContent(c.l));

  const sameKey = (s) => s.replace(/\s+/g, '');
  for (let i = 0; i < candidates.length; i++) {
    for (let j = i + 1; j < candidates.length; j++) {
      const a = candidates[i], b = candidates[j];
      if (sameKey(a.l) !== sameKey(b.l)) continue;      // 只认**同一串**
      if (boxes.length && !farApart(a.b, b.b)) continue; // 有坐标 ⇒ 还必须是**不同位置**
      droppedIdx.add(a.i); droppedIdx.add(b.i);
      basis = boxes.length ? 'same-string-different-position' : 'exact-repeat-no-coords';
    }
  }

  const kept = [], dropped = [];
  lines.forEach((l, i) => (droppedIdx.has(i) ? dropped : kept).push(l));
  const total = lines.filter((l) => l.trim()).length || 1;
  return { text: kept.join('\n'), kept, dropped, basis, droppedRatio: dropped.length / total };
}
