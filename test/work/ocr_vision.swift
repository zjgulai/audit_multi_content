// macOS Vision OCR —— 输出 JSON: [{text, confidence, bbox:[x,y,w,h]}]，bbox 归一化（原点左下）
// 用法: swift ocr_vision.swift <image> [--fast|--accurate]
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else { FileHandle.standardError.write("usage: ocr_vision.swift <image> [--fast|--accurate]".data(using: .utf8)!); exit(2) }
let path = args[1]
let accurate = !args.contains("--fast")

guard let img = NSImage(contentsOfFile: path),
      let tiff = img.tiffRepresentation,
      let bmp = NSBitmapImageRep(data: tiff),
      let cg = bmp.cgImage else {
    FileHandle.standardError.write("cannot load image: \(path)\n".data(using: .utf8)!)
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = accurate ? .accurate : .fast
request.usesLanguageCorrection = true
request.recognitionLanguages = ["en-US", "zh-Hans"]

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do { try handler.perform([request]) } catch {
    FileHandle.standardError.write("perform failed: \(error)\n".data(using: .utf8)!)
    exit(4)
}

var out: [[String: Any]] = []
if let obs = request.results {
    for o in obs {
        guard let top = o.topCandidates(1).first else { continue }
        let bb = o.boundingBox
        out.append([
            "text": top.string,
            "confidence": Double(top.confidence),
            "bbox": [Double(bb.origin.x), Double(bb.origin.y), Double(bb.size.width), Double(bb.size.height)]
        ])
    }
}
let data = try JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
