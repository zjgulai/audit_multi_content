import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1 else { print("{\"error\":\"no input\"}"); exit(1) }
var out: [[String: Any]] = []
for path in args.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        out.append(["file": path, "error": "cannot_load"]); continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { out.append(["file": path, "error": "ocr_failed"]); continue }
    var lines: [[String: Any]] = []
    for obs in (req.results ?? []) {
        guard let top = obs.topCandidates(1).first else { continue }
        let bb = obs.boundingBox
        lines.append(["text": top.string, "confidence": Double(top.confidence),
                      "bbox": [Double(bb.origin.x), Double(bb.origin.y), Double(bb.size.width), Double(bb.size.height)]])
    }
    out.append(["file": path, "width": cg.width, "height": cg.height, "lines": lines])
}
let data = try! JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted, .withoutEscapingSlashes])
FileHandle.standardOutput.write(data)
