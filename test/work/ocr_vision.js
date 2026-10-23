ObjC.import('Foundation');
ObjC.import('AppKit');
ObjC.import('Vision');

function run(argv) {
  const path = argv[0];
  const accurate = argv.indexOf('--fast') === -1;
  const data = $.NSData.dataWithContentsOfFile($(path));
  if (!data || data.js === undefined || data.js === null) {
    throw new Error('cannot read file: ' + path);
  }
  const req = $.VNRecognizeTextRequest.alloc.init;
  req.recognitionLevel = accurate ? 1 : 0; // 1 = accurate(VNRequestTextRecognitionLevelAccurate)
  req.usesLanguageCorrection = true;
  req.recognitionLanguages = $(['en-US', 'zh-Hans']);

  const handler = $.VNImageRequestHandler.alloc.initWithDataOptions(data, $({}));
  handler.performRequestsError($([req]), null);
  const results = req.results;
  const n = results.count;
  const out = [];
  for (let i = 0; i < n; i++) {
    const o = results.objectAtIndex(i);
    const cand = o.topCandidates(1);
    if (!cand || cand.count === 0) continue;
    const c = cand.objectAtIndex(0);
    const bb = o.boundingBox;
    out.push({
      text: ObjC.unwrap(c.string),
      confidence: c.confidence,
      bbox: [bb.origin.x, bb.origin.y, bb.size.width, bb.size.height].map(function (v) {
        return Math.round(v * 10000) / 10000;
      })
    });
  }
  return JSON.stringify(out, null, 1);
}
