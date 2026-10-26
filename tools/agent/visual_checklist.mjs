/**
 * visual_checklist.mjs —— 图单的**视觉核对清单**判据（Owner 2026-10-21）
 *
 * ── 为什么有它（病灶，实测）
 *   2026-10-21 那张母婴插画（床头柜上奶瓶倒着放）：`图片安全审查` skill **真的加载了**
 *   （会话日志里 `skill("图片安全审查")` 返回 `<skill_content>`，引擎 `image_skill_gate` 记 loaded），
 *   判定主体也确实写了结论 —— 但**画面那几个该看的地方一个都没被写到**：
 *   卡片上只有「北美本地化 / Listing 准确性」两条（模型侧按 OCR 德语文案给的），
 *   而那几类画面事实（婴幼儿姿势 / 产品状态 / 场景关系 / 隐私）**根本没出现**。
 *   ⇒ 结论：**「加载了 skill」不等于「执行了 skill 里那道视觉核对」**，
 *     而流程上没有任何东西会红。本文件就是那个红。
 *
 * ── 判据（只认这五类，缺一类就不收）
 *   婴幼儿姿势 / 婴儿睡眠位置 / 产品状态 / 场景关系 / 隐私
 *   每一项必须给：
 *     · 结论 ∈ {有, 无, 未测}
 *     · 「有」⇒ 必须带**依据**（≥6 字：看到了什么、在哪个位置）
 *     · 「未测」⇒ 必须带**原因**（≥4 字：为什么没测，如"画面读数没跑到"）
 *     · 「无」⇒ 依据可省（"无"本身就是结论；含糊的"无"由人复核，不在这里拦）
 *
 * ── 认哪些写法（宽进严出：认得出就算覆盖，判的还是结论本身）
 *   紧凑一行：`视觉核对：婴幼儿姿势=无；产品状态=有（床头柜上奶瓶倒置）；场景关系=无；隐私=无`
 *   分条：`- 婴幼儿姿势：无` ／ `产品状态：有（…）` ／ `【隐私】未测（画面读数没跑到）`
 *   ⚠️ 只认**类别名 + 结论**同时出现在**同一行/同一分句**里 —— 否则"整段里提过隐私两个字"
 *     就会算覆盖，那这条判据等于恒真（本仓栽过：判据恒绿 = 注释）。
 *
 * ── 边界
 *   · 本文件**只判"有没有写"，不判"写得对不对"**：写的对不对要人复核（它是主模型的读数，
 *     不是原图）—— 把"判内容"混进来，会变成用一句话骗过闸门。
 *   · 纯函数、零 I/O、零网络：喂字符串就能证，所以它能进单测。
 */

/** 五类视觉核对（顺序即建议书写顺序；缺一类不收）。 */
export const VISUAL_CATEGORIES = Object.freeze([
  { key: 'infant_posture', label: '婴幼儿姿势' },
  { key: 'infant_sleep_position', label: '婴儿睡眠位置' },
  { key: 'product_state', label: '产品状态' },
  { key: 'scene_relation', label: '场景关系' },
  { key: 'privacy', label: '隐私' },
]);

/** 结论闭集（只认这三个；"未见异常"这类写法按同义词归一到"无"）。 */
const VERDICT_ALIASES = Object.freeze([
  ['未测', ['未测', '没测', '未判', '没判过']],
  ['有', ['有', '存在', '出现', '存在异常']],
  ['无', ['无', '没有', '未见', '没发现', '不存在']],
]);

/** 把一行里的结论词归一。**长词优先**（"未测"必须在"无"之前判，否则"未测"会被读成"无"）。 */
function verdictOf(segment) {
  for (const [canon, words] of VERDICT_ALIASES) {
    for (const w of words) {
      // 「无」是单字，必须带边界：`\\b` 对中文无效，改用"非汉字前后"判
      const re = w.length === 1 ? new RegExp(`(^|[^\\u4e00-\\u9fff])${w}([^\\u4e00-\\u9fff]|$)`) : new RegExp(w);
      if (re.test(segment)) return canon;
    }
  }
  return null;
}

/** 这一行是不是 Markdown 表格行（模型很爱用表；2026-10-21 实测那一单就是表）。 */
function isTableRow(segment) {
  return String(segment).trim().startsWith('|');
}

/** 表格行里「标签 → 结论」那一格（只认紧跟在标签后的第一格）。 */
function tableCells(segment, label) {
  const cells = segment.split('|').map((c) => c.trim()).filter((c) => c.length > 0);
  const idx = cells.findIndex((c) => c.replace(/\*\*/g, '').trim() === label || c.includes(label));
  return idx < 0 ? null : { cells, idx };
}

/** 结论判定：表格行只看「标签后那一格」，否则看整段。 */
function verdictIn(segment, label) {
  if (isTableRow(segment)) {
    const t = tableCells(segment, label);
    if (t) {
      // Read only the leading clause in the verdict cell. Explanatory text can
      // mention another category's verdict (e.g. "场景关系＝有") and must not
      // override this row's own conclusion.
      const cell = (t.cells[t.idx + 1] ?? '').replace(/\*\*/g, '').trim();
      return verdictOf(cell.split(/[；;|]/, 1)[0]);
    }
  }
  return verdictOf(String(segment).replace(/\*\*/g, ''));
}

/** 依据文本：表格行取「结论之后的那一格」，普通行剥掉类别名与结论词后剩下的部分。
 *
 *  ⚠️ 2026-10-21 实测修（**假阳性**）：模型用表格交了清单，其中一格的依据是
 *     「画面读数为「床铺、枕头、被子（正在被使用）」，而同一张床上同时有婴幼儿 ⇒ 松软寝具…」——
 *     旧实现**优先取第一个括号**，于是依据被读成「正在被使用」（5 字）⇒ 判「没给依据」。
 *     依据本来写得很足，是判据自己抠错了。⇒ 表格行按列取、普通行取整段，括号不再是首选。
 */
function basisOf(segment, label) {
  if (isTableRow(segment)) {
    const t = tableCells(segment, label);
    if (t) {
      const rest = t.cells.slice(t.idx + 1)
        .filter((c) => !/^(有|无|未测)$/.test(c.replace(/\*\*/g, '').trim()));
      const joined = rest.join('；').replace(/\*\*/g, '').trim();
      if (joined) return joined;
    }
  }
  let rest = String(segment);
  if (label) rest = rest.split(label).join(' ');
  for (const [, words] of VERDICT_ALIASES) for (const w of words) rest = rest.split(w).join(' ');
  rest = rest.replace(/\*\*/g, '').replace(/[：:＝=，,。；;|]/g, ' ').trim();
  return rest;
}

/**
 * Some valid reports put each category's conclusion in a numbered heading and
 * its evidence in the following bullet rows (for example `**1. 婴幼儿姿势：有**`
 * followed by `- 依据：...`). Keep those rows attached to that category until
 * the next category/numbered item. Without this, the heading number (`1.`) was
 * mistaken for evidence and every detailed checklist was rejected as basis-free.
 */
function categoryEvidenceLines(text, label) {
  const lines = String(text ?? '').split(/\r?\n/);
  const start = lines.findIndex((line) => line.includes(label) && verdictIn(line.trim(), label));
  if (start < 0) return [];
  const first = lines[start].trim();
  const out = [first];
  const numberedItem = /^\s*(?:[-*+]\s+)?\*{0,2}\d+[.、]/.test(first);
  const categoryListItem = /^\s*[-*+]\s+/.test(first) && first.includes(label);
  const table = isTableRow(first);
  if (!numberedItem && !categoryListItem && !table) return out;
  for (let i = start + 1; i < lines.length; i++) {
    const raw = lines[i];
    const line = raw.trim();
    if (!line) {
      if (out.length > 1) break;
      continue;
    }
    if (/^#{1,6}\s/.test(line)
      || /^\*{0,2}\d+[.、]/.test(line)) break;
    const nextCategory = VISUAL_CATEGORIES
      .filter((cat) => cat.label !== label)
      .some((cat) => line.includes(cat.label) && verdictIn(line, cat.label));
    if (nextCategory) break;
    if (table && isTableRow(line)) { out.push(line); continue; }
    if (/^[-*+]\s+/.test(line) || /^\s{2,}[-*+]\s+/.test(raw)) {
      out.push(line);
      continue;
    }
    break;
  }
  return out;
}

/** 切成分句：先按行，再按 `；`／`;`。一行里塞多类（紧凑写法）也认得出来。 */
function segmentsOf(text) {
  const out = [];
  for (const line of String(text ?? '').split(/\r?\n/)) {
    const s = line.trim();
    if (!s) continue;
    // 表格行整行算一个分句：行内常有「；」，切开就把同一行的依据劈成两半（实测踩过）
    if (isTableRow(s)) { out.push(s); continue; }
    for (const seg of s.split(/[；;]/)) {
      const t = seg.trim();
      if (t) out.push(t);
    }
  }
  return out;
}

/**
 * 睡眠位置可以用父项 + 缩进子项表达逐场景读数，例如：
 *
 *   - 婴儿睡眠位置：无。依据（逐场景）：
 *     - 场景组①（大床同床）：婴幼儿仰卧；
 *     - 场景组②（婴儿床）：婴幼儿仰卧。
 *
 * 只把紧跟在该父项后的缩进列表并入睡眠位置证据；到下一个视觉类别即停止。
 * 这样既接受清晰的 Markdown 层级，也不把正文其他位置提到的睡姿误当成清单复述。
 */
function sleepPositionEvidence(text, categoryText) {
  const lines = categoryEvidenceLines(text, '婴儿睡眠位置');
  return lines.length ? lines.join(' ') : categoryText;
}

/* ═══════════════ 「同上」指代：理由写在上一行，本身不是理由 ═══════════════
 *
 * ── 病灶（2026-10-22 生产实测，`om_x100b62ab067718a4b07f19a08c44374`）
 *   真实链回答的第七节是这样的表格：
 *
 *     | 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |
 *     | 场景关系 | **未测** | 同上 |
 *
 *   「同上」是**人写表格的正常写法**，指的就是紧挨着上一条那句原因。
 *   而旧判据把这一格当成「只有 2 个字 ⇒ 没给原因」⇒ 整份**写得很完整**的报告被判成
 *   「审查流程没有完成」⇒ 群里收到「请重新发送原图」（同一形状当天已发生 4 次）。
 *
 * ── 只接受一种继承，其余一律不继承（修假阳性不许把判据放成恒绿）
 *   ① 上一条**是另一类视觉核对**（同一份清单里的上一行）；
 *   ② 上一条的**结论相同**（「同上」字面就是「同上一条的结论与理由」；
 *      跨结论的「同上」含义不明，宁可判红也不猜）；
 *   ③ 上一条的**理由本身可用**（非空、不是另一句「同上」、≥4 字）。
 *   三条缺一条 ⇒ 原样留着 ⇒ 仍按「没给原因/没给依据」判红。
 */
const ANAPHORA_HEAD = /^(?:同上(?:一?[条行格处项])?|同前(?:一?[条行格处项])?)/;

/** 拆出「同上」这类指代：`{token:'同上', tail:'（其余自己写的话）'}`；不是指代回 null。 */
function splitAnaphora(basis) {
  const s = String(basis ?? '').replace(/\*\*/g, '').trim();
  const m = s.match(ANAPHORA_HEAD);
  return m ? { token: m[0], tail: s.slice(m[0].length).trim() } : null;
}

/** 这一格理由自己站得住吗（空 / 又一句「同上」 / 太短 都不算）。 */
function usableBasis(basis) {
  const s = String(basis ?? '').trim();
  return s.length >= 4 && !splitAnaphora(s);
}

/**
 * 把「同上」补成它真正指着的那条理由（就地改 `found`，返回同一个对象）。
 * 补不上就**什么都不做** —— 由后面的长度判据照原样判红。
 */
function resolveAnaphora(found) {
  const ordered = Object.values(found).sort((a, b) => a.seq - b.seq);
  let prev = null;
  for (const hit of ordered) {
    const ana = splitAnaphora(hit.basis);
    hit.anaphora = ana ? ana.token : null;
    if (ana && prev && prev.verdict === hit.verdict && usableBasis(prev.basis)) {
      hit.basis = [prev.basis, ana.tail].filter(Boolean).join(' ');
      hit.inheritedFrom = prev.label ?? null;
      hit.anaphora = null;
    }
    prev = hit;
  }
  return found;
}

/**
 * 判一份回复文本有没有覆盖五类视觉核对。
 * @param {string} text - 判定主体的回复（或报告正文）
 * @returns {{ok:boolean, missing:string[], weak:Array<{label:string,verdict:string}>,
 *            found:object, reason:string}}
 */
export function checkVisualChecklist(text, opts = {}) {
  const found = {};
  let seq = 0;
  for (const seg of segmentsOf(text)) {
    for (const cat of VISUAL_CATEGORIES) {
      if (found[cat.key]) continue;
      if (!seg.includes(cat.label)) continue;
      const verdict = verdictIn(seg, cat.label);
      if (!verdict) continue;                       // 提了名字没给结论 ⇒ 不算覆盖
      found[cat.key] = { verdict, basis: basisOf(seg, cat.label), text: seg.slice(0, 120),
                         label: cat.label, seq: seq++ };
    }
  }
  resolveAnaphora(found);

  const missing = [];
  const weak = [];          // 给日志/报告看的一句话（含判据自己的诊断）
  const weakItems = [];     // 给**人**看的口径：只留类别名与结论，不带判据术语
  for (const cat of VISUAL_CATEGORIES) {
    const hit = found[cat.key];
    if (!hit) { missing.push(cat.label); continue; }
    const evidenceLines = categoryEvidenceLines(text, cat.label);
    if (evidenceLines.length > 1) {
      const continuation = evidenceLines.slice(1).join(' ')
        .replace(/\*\*/g, '').replace(/\b\d+[.、]\s*/g, ' ')
        .replace(/[-*+]\s*(?:依据|原因)?[:：]?/g, ' ').trim();
      hit.basis = [hit.basis, continuation].filter(Boolean).join(' ').trim();
      hit.text = evidenceLines.join(' ');
    }
    if (hit.verdict === '有' && hit.basis.length < 6) {
      weak.push(`${cat.label}（判"有"但没给依据）`);
      weakItems.push({ label: cat.label, verdict: hit.verdict });
    }
    if (hit.verdict === '未测' && hit.basis.length < 4) {
      // 「同上」补不上时，报错文案要说得出**它是怎么失败的** —— 否则下一次又是
      // 「判"未测"但没给原因」这一句，看的人不知道到底是没写、还是写了指代没指到。
      weak.push(hit.anaphora
        ? `${cat.label}（判"未测"，只写了「${hit.anaphora}」而上面没有可用的原因）`
        : `${cat.label}（判"未测"但没给原因）`);
      weakItems.push({ label: cat.label, verdict: hit.verdict });
    }
  }

  if (missing.length) {
    return { ok: false, missing, weakItems, found, reason: `缺 ${missing.length} 类视觉核对：${missing.join('、')}` };
  }
  if (weak.length) {
    return { ok: false, missing: [], weakItems, found, reason: `视觉核对的结论没写清：${weak.join('、')}` };
  }

  // 读数里若逐人给出了婴儿睡姿，回复的独立睡眠位置项必须复述这些姿势。
  // 这能挡住「画面层看见侧卧、审查结论却只说同床」以及遗漏读数的情况。
  const sleepPositions = Array.isArray(opts.sleepPositions) ? opts.sleepPositions : [];
  const sleepText = sleepPositionEvidence(text, String(found.infant_sleep_position?.text ?? ''));
  const poseAliases = {
    '仰卧': ['仰卧', '仰躺'], '侧卧': ['侧卧', '侧躺'], '俯卧': ['俯卧', '趴卧'],
    '看不清': ['看不清', '无法辨认', '无法确认'],
  };
  const expectedCounts = new Map();
  for (const item of sleepPositions) {
    const pose = String(item?.position ?? item ?? '').trim();
    if (!pose || pose === '不适用') continue;
    expectedCounts.set(pose, (expectedCounts.get(pose) ?? 0) + 1);
  }
  const omittedPoses = [];
  for (const [pose, count] of expectedCounts) {
    const aliases = poseAliases[pose];
    const actual = aliases
      ? Math.max(0, ...aliases.map((alias) => sleepText.split(alias).length - 1))
      : 0;
    for (let n = actual; n < count; n++) {
      const first = sleepPositions.find((x) => String(x?.position ?? x ?? '').trim() === pose);
      omittedPoses.push(first ?? pose);
    }
  }
  // 面板级读数不能被一条总括性的「仰卧/侧卧」吞掉：对应面板与姿势必须在同一分句出现。
  const sleepSegments = sleepText.split(/[；;|\n]/).map((x) => x.trim()).filter(Boolean);
  const panelAxis = (panel) => /上/.test(panel) ? 'upper' : /下/.test(panel) ? 'lower' : '';
  const axisAliases = {
    upper: ['顶部', '上方', '上部', '上面板', '上半部分', '上图'],
    lower: ['底部', '下方', '下部', '下面板', '下半部分', '下图'],
  };
  const compact = (value) => String(value ?? '').replace(/[\s　]/g, '').replace(/[Ａ-Ｚａ-ｚ]/g,
    (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xfee0)).toUpperCase();
  const imageKey = (value) => compact(value).replace(/^图/, '图');
  const axisOf = (panel) => /上/.test(panel) ? 'upper' : /下/.test(panel) ? 'lower' : '';
  const locationPattern = /(左上|右上|上左|上右|左下|右下|下左|下右|顶部|底部|上方|下方|上部|下部|上面板|下面板|上半部分|下半部分)/;
  // Reports sometimes rename the visual-model coordinates to lettered panels.
  // Trust A/B only when this same report explicitly maps each label to a location
  // and that location identifies exactly one sleep-reading in the image.
  const panelAliases = new Map();
  const aliasTargets = new Map();
  const textImages = new Set(sleepPositions.map((x) => imageKey(x?.image)).filter(Boolean));
  for (const m of String(text ?? '').matchAll(/(?:图\s*(\d+)\s*)?面板\s*([A-ZＡ-Ｚ])\s*[（(]([^）)]+)[）)]/gu)) {
    const alias = `面板${compact(m[2])}`;
    const location = m[3].match(locationPattern)?.[0] ?? '';
    if (!location) continue;
    const image = m[1] ? `图${m[1]}` : (textImages.size === 1 ? [...textImages][0] : '');
    if (!image) continue; // no image anchor and multiple images ⇒ cannot safely bind the alias
    const candidates = sleepPositions.filter((item) => {
      if (imageKey(item?.image) !== image) return false;
      const panel = String(item?.panel ?? '').trim();
      if (panel === location) return true;
      const axis = axisOf(panel);
      const locationAxis = axisOf(location);
      if (!axis || axis !== locationAxis) return false;
      const sameAxis = sleepPositions.filter((other) => imageKey(other?.image) === image
        && axisOf(String(other?.panel ?? '').trim()) === axis);
      return sameAxis.length === 1;
    });
    if (candidates.length !== 1) continue;
    const target = candidates[0];
    const targets = aliasTargets.get(alias) ?? new Set();
    targets.add(target);
    aliasTargets.set(alias, targets);
  }
  // Skill reports may declare panels as headings with the vertical position
  // later in the same heading, e.g. `面板 A —— 错误示范（上，y≈90–440）`.
  // Bind A/B only when that upper/lower direction identifies exactly one
  // sleep-reading in the image; never infer from the letter alone.
  for (const m of String(text ?? '').matchAll(/(?:^|\n)\s*\*{0,2}面板\s*([A-ZＡ-Ｚ])\s*[—–-]{1,}([^\n]+)/gu)) {
    const alias = `面板${compact(m[1])}`;
    const image = textImages.size === 1 ? [...textImages][0] : '';
    if (!image) continue;
    const parenthetical = m[2].match(/[（(]([^）)]+)[）)]/)?.[1] ?? '';
    const direction = parenthetical.match(/(?:^|[，,\s])([上下])(?:[，,\s)）]|$)/u)?.[1] ?? '';
    if (!direction) continue;
    const axis = direction === '上' ? 'upper' : 'lower';
    const candidates = sleepPositions.filter((item) => imageKey(item?.image) === image
      && axisOf(String(item?.panel ?? '').trim()) === axis);
    if (candidates.length !== 1) continue;
    const targets = aliasTargets.get(alias) ?? new Set();
    targets.add(candidates[0]);
    aliasTargets.set(alias, targets);
  }
  for (const [alias, targets] of aliasTargets) {
    if (targets.size !== 1) continue;
    const target = [...targets][0];
    const prior = panelAliases.get(target) ?? new Set();
    prior.add(alias);
    panelAliases.set(target, prior);
  }
  const imageIsExplicit = (segment, image) => {
    const normalized = String(image ?? '').replace(/\s+/g, '');
    return normalized.length > 0 && segment.replace(/\s+/g, '').includes(normalized);
  };
  for (const item of sleepPositions) {
    const panel = String(item?.panel ?? '').trim();
    const pose = String(item?.position ?? '').trim();
    if (!panel || !pose || pose === '不适用') continue;
    const poseNames = poseAliases[pose] ?? [pose];
    const axis = panelAxis(panel);
    // 报告常把「右上 / 右下」写成「顶部 / 底部」或「上方面板 / 下方面板」。
    // 只在该图的对应行/列唯一时接受方位简称，避免两块上方面板被同一个「顶部」混淆。
    const sameAxis = axis ? sleepPositions.filter((other) => other?.image === item?.image
      && panelAxis(String(other?.panel ?? '').trim()) === axis) : [];
    const axisIsUnique = sameAxis.length === 1;
    const panelNames = [panel];
    if (axis && axisIsUnique) panelNames.push(...axisAliases[axis]);
    const axisRepeatedAcrossImages = axis && sleepPositions.some((other) => other !== item
      && other?.image !== item?.image && panelAxis(String(other?.panel ?? '').trim()) === axis);
    const panelAliasNames = [...(panelAliases.get(item) ?? [])];
    const matched = sleepSegments.some((seg) => [...panelNames, ...panelAliasNames].some((name) => {
      if (panelAliasNames.includes(name)) return compact(seg).includes(compact(name));
      return seg.includes(name);
    })
      && poseNames.some((alias) => seg.includes(alias))
      && (!axisRepeatedAcrossImages || imageIsExplicit(seg, item?.image)));
    if (!matched) omittedPoses.push(item);
  }
  if (omittedPoses.length) {
    return {
      ok: false, missing: [], found,
      reason: `画面读数记录了婴儿睡姿（${omittedPoses.map((x) => typeof x === 'string'
        ? x : `${x?.image ?? '图'}${x?.panel ? ` ${x.panel}` : ''}：${x?.position ?? '未给'}`).join('、')}），视觉核对项未逐面板复述姿势`,
    };
  }
  const unsafePosture = sleepPositions.filter((item) => ['侧卧', '俯卧'].includes(String(item?.position ?? item ?? '').trim()));
  if (unsafePosture.length && found.infant_sleep_position?.verdict !== '有') {
    return { ok: false, missing: [], found, reason: '画面读数显示侧卧/俯卧，但「婴儿睡眠位置」没有判为有问题' };
  }
  const unclearPosture = sleepPositions.filter((item) => String(item?.position ?? item ?? '').trim() === '看不清');
  if (unclearPosture.length && found.infant_sleep_position?.verdict !== '未测') {
    return { ok: false, missing: [], found, reason: '画面读数无法确认睡姿，但「婴儿睡眠位置」没有标为未测' };
  }

  // ── 读数边界：读数里明明有「倒置/侧放/悬空/贴边」的容器，清单却一个字没提 ⇒ 红 ──────
  //   这是唯一能咬到「看见了却装没看见」的判据；读数没看见时它不咬（那是读数的账，
  //   见 scene.mjs 的容器必列规则）。opts.abnormal 由调用方从画面读数里取。
  const abnormal = Array.isArray(opts.abnormal) ? opts.abnormal : [];
  const unmentioned = [];
  for (const item of abnormal) {
    const what = String(item?.what ?? '');
    const key = (what.match(/[瓶杯罐盒壶]/) || [null])[0];
    if (!key) continue;
    const said = Object.values(found).some((f) => f.verdict === '有' && String(f.text).includes(key));
    if (!said) unmentioned.push(`${what}（${item?.orientation ?? '姿态异常'}）`);
  }
  if (unmentioned.length) {
    return {
      ok: false, missing: [], found,
      reason: `画面读数里有姿态异常的容器（${unmentioned.join('、')}），视觉核对清单没提`,
    };
  }

  return { ok: true, missing: [], found, reason: '' };
}

/**
 * Full skill completion receipt. Loading the skill and presenting five visual labels are not enough:
 * require evidence that the workflow's scope, extraction, claim decomposition, 4A, 4B and consistency
 * checks were actually returned in this review. This is a fail-closed output contract, not a claim
 * that headings alone prove the underlying analysis is correct.
 */
/* ═══════════ 逐面板睡姿：模型不写，代码搬（Owner 2026-10-26 批准「推荐 A」）═══════════
 *
 * ── 病灶（2026-10-26 真单 `om_x100b62dbe6ca94b8cf023280d301600`，15:00 那张图）
 *   画面读数**明明逐面板读出了姿势**：
 *     `图 1 右上：仰卧`、`图 1 右下：仰卧`（`scene.mjs::infantSleepReadings` 有这两行）
 *   而模型交的核对项只写了总括 —— 闸门原话：
 *     `画面读数记录了婴儿睡姿（…），视觉核对项未逐面板复述姿势`
 *   ⇒ 整单被判「图片安全审查全流程未完成」⇒ 三态结论被扣下 ⇒ 群里收到「审查未完成」。
 *   当天这条闸门触发 **12 次**，其中 **6 次**都是同一个原因 ⇒ 图单几乎出不来 PRD 三态卡。
 *
 * ── 为什么「代码搬」在这里是**对的**（不是造证据）
 *   搬的是**画面读数里的原文值**（面板 + 姿势），与 `renderMerged` 搬库侧依据行、
 *   `dual_track` 搬结论行**同一条分工**：模型不写，代码搬，**搬的必须是已经拿到的证据**。
 *   反过来，三条边界一条都不许松 —— 违反任何一条就退回「不补」：
 *     ① **读数里没有逐面板** （`panel` 为空）⇒ 不补（不许凭一个总括姿势编出「右上/右下」）；
 *     ② **核对项本身不存在/没判出结论** ⇒ 不补（不许替模型造出整个「婴儿睡眠位置」项）；
 *     ③ **模型已经逐面板复述过** ⇒ 不补（幂等：跑第二遍一个字不加）。
 *   ⚠️ 补写**改的是要出门的正文**（走进 `res.answer`，卡上与报告里都看得见），
 *     并在日志里留一行 `🖼 逐面板复述：代码补写 …` —— 谁的功劳、补了什么，都查得到。
 */
export function restatePerPanelSleep(text, sleepPositions = []) {
  const s = String(text ?? '');
  const rows = (Array.isArray(sleepPositions) ? sleepPositions : [])
    .map((x) => ({
      image: String(x?.image ?? '').trim(),
      panel: String(x?.panel ?? '').trim(),
      position: String(x?.position ?? '').trim(),
    }))
    // 边界①：读数没给面板 ⇒ 不参与补写（无从"逐面板"）
    .filter((x) => x.panel && x.position && x.position !== '不适用');
  if (!rows.length) return { text: s, added: [], detail: '' };
  const lines = s.split(/\r?\n/);
  // 边界②：那一项必须**已经存在**（有结论），否则不补
  const lineIdx = lines.findIndex((ln) => /婴儿睡眠位置/.test(ln) && verdictIn(ln, '婴儿睡眠位置'));
  if (lineIdx < 0) return { text: s, added: [], detail: '' };
  const poseAliases = {
    '仰卧': ['仰卧', '仰躺'], '侧卧': ['侧卧', '侧躺'], '俯卧': ['俯卧', '趴卧'],
    '看不清': ['看不清', '无法辨认', '无法确认'],
  };
  // 判据与闸门同形：以「该类的证据行」为范围、按 `；;|\n` 切分句，面板与姿势必须在同一分句
  const segs = lines.filter((ln) => /婴儿睡眠位置/.test(ln)).join(' ')
    .split(/[；;|\n]/).map((x) => x.trim()).filter(Boolean);
  const missing = rows.filter((r) => !segs.some((seg) => seg.includes(r.panel)
    && (poseAliases[r.position] ?? [r.position]).some((a) => seg.includes(a))));
  // 边界③：都复述过了 ⇒ 一个字不加（幂等）
  if (!missing.length) return { text: s, added: [], detail: '' };
  const detail = '位置明细：' + missing
    .map((r) => `${r.image ? `${r.image} ` : ''}${r.panel}＝${r.position}`).join('；') + '。';
  lines[lineIdx] = `${lines[lineIdx].replace(/\s*$/, '')} ${detail}`;
  return { text: lines.join('\n'), added: missing, detail };
}

export function checkImageSkillWorkflow(text) {
  const s = String(text ?? '');
  const stages = [
    ['审核对象与范围', /审核对象与范围|审核范围/],
    ['视觉分析与 OCR', /(视觉分析|图像内容提取)[\s\S]{0,240}OCR|OCR[\s\S]{0,240}(视觉分析|图像内容提取)/],
    ['主张拆分与核查清单', /主张拆分|主张核查清单|核查清单/],
    ['4A 规则符合性', /4A[：:、\s\S]{0,80}规则符合性|规则符合性[\s\S]{0,80}4A/],
    ['4B 事实准确性核查', /4B[：:、\s\S]{0,80}事实准确性|事实准确性[\s\S]{0,80}4B/],
    ['图文一致性', /图文一致性/],
  ];
  const missing = stages.filter(([, re]) => !re.test(s)).map(([label]) => label);
  // Infant sleep is high impact: the skill requires an authoritative source check, not just a rule hit.
  const sleepReview = /婴儿|婴幼儿|睡眠|仰卧|侧卧|俯卧|同床/.test(s);
  const hasAuthoritativeSource = /AAP|HealthyChildren|pediatrics\.aappublications\.org|healthychildren\.org/i.test(s);
  if (sleepReview && !hasAuthoritativeSource) missing.push('婴儿安全事实的权威来源核查（AAP/HealthyChildren）');
  return {
    ok: missing.length === 0,
    missing,
    reason: missing.length ? `图片安全审查 skill 全流程缺项：${missing.join('、')}` : '',
  };
}

/** 给提示词用的清单说明（模板与手册共用**同一份**，别各抄一遍）。 */
export function visualChecklistInstructions() {
  return [
    '【★ 第 0 条之三 —— 图单必须交「视觉核对清单」（缺项本单**不收**）】',
    '在回复里**逐项**写下面五类，每项给结论与依据：',
    ...VISUAL_CATEGORIES.map((c) => `  · ${c.label}`),
    '  · 「婴儿睡眠位置」必须单独写明每个睡眠场景中婴儿的仰卧/侧卧/俯卧/看不清；不能用「姿势正常」或「安全」代替。',
    '  · 画面没有婴儿睡眠场景时，写「婴儿睡眠位置=无（画面没有婴儿睡眠场景）」；有但无法辨认时写「未测」并说明原因。',
    '  · 画面读数为侧卧/俯卧时该项必须判「有」；姿势读数为看不清/未给时必须判「未测」，不得当成无问题。',
    '  · 同一张图有多个面板/婴儿时逐个核对，分别标明面板；床共享风险与睡姿是两个独立问题。',
    '结论只能是 `有` / `无` / `未测`：',
    '  · `有` ⇒ **必须写依据**（看到了什么、在哪个位置，例如「产品状态：有（床头柜上的奶瓶倒置）」）；',
    '  · `无` ⇒ 直接写「无」（不许写「未见明显问题」这类含糊话）；',
    '  · `未测` ⇒ **必须写原因**（例如「画面读数没跑到」）。',
    '依据只能来自**画面读数**（守衡给的那一格），不许拿 OCR 文字冒充画面事实。',
    '每条问题的「位置」也必须按四形态写：`区域词，图 N 第 X 处`（区域词只许 顶部/中部/底部/左侧/右侧；',
    '第 X 处 = 图内文字块阅读顺序行号）——**不许写裸「图 1」或「图 1 主视觉」**：出口闸 R3 会判红。',
  ].join('\n');
}
