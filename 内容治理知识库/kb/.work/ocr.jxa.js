ObjC.import('Foundation');
ObjC.import('Vision');
ObjC.import('AppKit');

// 用法: osascript -l JavaScript ocr.jxa.js <out.json> <img1> [img2 ...]
// 说明: JXA 的 console.log 走 stderr，因此结果写入调用方指定的文件。

// ============================================================================
// 2026-09-24 修复记录（原实现见 ocr.jxa.js.bak-20260924-104442）
//
// 【症状】77 条缓存里 28 条含 U+FFFF、0 条识别出中文、182 个破损字符；
//         拉丁字符也连带走形（'Superfast Portable' → 'SutwfagtPo￿lè8￿bY'）。
//
// 【根因】recognitionLevel = 1(accurate) 在本机只支持 6 种语言：
//           en-US / fr-FR / it-IT / de-DE / es-ES / pt-BR  —— 不含中文。
//         原配置却向它请求 `['zh-Hans','en-US']`。Vision 对不支持的语言**静默忽略**
//         （不报错、不抛异常），退回纯拉丁识别 → 汉字成 U+FFFF、整行丢失、拉丁走形。
//         实测（macOS 26.6.2 / revision 3）：
//           accurate(1) 支持 6 种；fast(0) 支持 30 种（含 zh-Hans zh-Hant yue-Hans yue-Hant
//           ko-KR ja-JP ru-RU uk-UA th-TH vi-VT ar-SA ars-SA tr-TR id-ID cs-CZ da-DK
//           nl-NL no-NO nn-NO nb-NO ms-MY pl-PL ro-RO sv-SE）。
//         → 中文只有 fast(0) 支持，这是本 bug 的全部原因。
//
// 【次生问题一】recognitionLanguages 只有**第一个元素生效**，其余为装饰。
//         实测：列表以 zh-Hans 开头 → 汉字 101 / 泰文 0；以 th-TH 开头 → 汉字 0 / 泰文 157。
//         所以"把 de/fr/es/th 追加到末尾"是无效修复，一个列表无法服务多语种素材。
//
// 【次生问题二 · 已澄清】一度以为 auto-detect 会静默丢弃阿拉伯语，实测是**我的测试写错了**：
//         那一臂没有设 automaticallyDetectsLanguage、也没传语言列表，等于"什么都不指定"，
//         才得到 5 行 / 0 个阿拉伯字符。用真正的 auto-detect 复测：
//           阿拉伯物料（recvw2wE9MFflB）→ 8 行 / 51 个阿拉伯字符，逐字正确；
//           且与批次位置无关（单独跑、排第 5 位、中文/德语图之后跑，结果一致）。
//         → 结论：auto-detect 已覆盖 ar-SA，**不需要**额外的阿拉伯语兜底遍。
//
// 【最终修法】
//         第一遍：recognitionLevel=0 + automaticallyDetectsLanguage=true（不传语言列表）
//         第二遍：recognitionLevel=0 + recognitionLanguages=['ar-SA']，仅当第一遍没认出阿拉伯字符时跑
//         合并：第一遍全保留，第二遍只追加"含阿拉伯字符且未出现过"的行
//
// 【实测效果】317 个图片条目（165 个记录）：
//           修复前 accurate+zh/en : 汉字 0     / U+FFFF 182 / 泰文 0
//           修复后 fast+zh-Hans   : 汉字 1171  / U+FFFF 0   / 泰文 0
//           现行 fast+auto         : 汉字 5640  / U+FFFF 0   / 泰文 345 / 阿拉伯 51+
//
// 【仍未修，非本次引入】
//         · confidence 不可用：JXA 桥接把它压成 0.5/0.3（偶尔 1）三个离散值，
//           不是 Vision 的真实连续置信度，不能做质量门控。用 ocr_char_count 代替。
//         · ocr.swift 已无法编译（SDK/toolchain 不匹配），JXA 是唯一可用路径。
//         · 极长图（如 2096×16776）单次识别质量下降，必要时需切图后分块识别。
// ============================================================================
const RECOGNITION_LEVEL = 0;          // 0 = fast。必须为 0：中文只在 fast 下受支持
const AUTO_DETECT_LANGUAGE = true;    // 第一遍按图检测语言
// 不设第二遍：auto-detect 已覆盖 ar-SA（见上，实测 8 行/51 字符）。保留 ar-SA 会把请求数翻倍且无收益。

const argv = $.NSProcessInfo.processInfo.arguments.js;
const outPath = ObjC.unwrap(argv[4]);
const inputs = argv.slice(5).map(function (x) { return ObjC.unwrap(x); });

function recognise(url, langs) {
  const req = $.VNRecognizeTextRequest.alloc.init;
  req.recognitionLevel = RECOGNITION_LEVEL;
  if (langs) {
    req.recognitionLanguages = $(langs);
  } else if (AUTO_DETECT_LANGUAGE) {
    req.automaticallyDetectsLanguage = true;   // 不传语言列表，避开"只有第一个生效"的陷阱
  }
  req.usesLanguageCorrection = true;
  const handler = $.VNImageRequestHandler.alloc.initWithURLOptions(url, $({}));
  handler.performRequestsError($([req]), $());
  const res = req.results;
  const lines = [];
  for (let i = 0; i < res.count; i++) {
    const obs = res.objectAtIndex(i);
    const cands = obs.topCandidates(1);
    if (cands.count === 0) continue;
    const c = cands.objectAtIndex(0);
    const bb = obs.boundingBox;
    lines.push({ text: ObjC.unwrap(c.string), confidence: c.confidence,
                 bbox: [bb.origin.x, bb.origin.y, bb.size.width, bb.size.height] });
  }
  return lines;
}

function ocr(path) {
  const url = $.NSURL.fileURLWithPath($(path));
  return { file: path, lines: recognise(url, null) };
}

const out = inputs.map(ocr);
const payload = $.NSString.alloc.initWithUTF8String(JSON.stringify(out));
payload.writeToFileAtomicallyEncodingError(outPath, true, $.NSUTF8StringEncoding, $());
