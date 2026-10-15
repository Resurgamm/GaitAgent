// Generates a synthetic clip for exercising the ChildGait demo.
//
//   swift MakeSessionVideo.swift out.mp4 sagittal [seconds]
//   swift MakeSessionVideo.swift out.mp4 coronal  [seconds]
//
// `sagittal` draws a figure crossing the frame side-on; `coronal` draws one walking toward the
// camera, growing as it approaches. Both mimic what the two cameras in the capture protocol see.
//
// The figure is a stick figure, so ML Kit will not detect a pose in it. That is fine for
// exercising the report and playback, but the skeleton overlay needs real footage.

import AVFoundation
import CoreGraphics
import Foundation

guard CommandLine.arguments.count > 2 else {
    print("usage: MakeSessionVideo.swift <out.mp4> <sagittal|coronal> [seconds]")
    exit(2)
}

let outPath = CommandLine.arguments[1]
let mode = CommandLine.arguments[2].lowercased()
let seconds = CommandLine.arguments.count > 3 ? Double(CommandLine.arguments[3])! : 4.0

guard mode == "sagittal" || mode == "coronal" else {
    print("mode must be 'sagittal' or 'coronal'")
    exit(2)
}

let width = 640, height = 360
let fps: Int32 = 30
let totalFrames = Int(seconds * Double(fps))

let outURL = URL(fileURLWithPath: outPath)
try? FileManager.default.removeItem(at: outURL)

let writer = try AVAssetWriter(outputURL: outURL, fileType: .mp4)
let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: width,
    AVVideoHeightKey: height,
])
input.expectsMediaDataInRealTime = false

let adaptor = AVAssetWriterInputPixelBufferAdaptor(
    assetWriterInput: input,
    sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32ARGB),
        kCVPixelBufferWidthKey as String: width,
        kCVPixelBufferHeightKey as String: height,
    ]
)

writer.add(input)
writer.startWriting()
writer.startSession(atSourceTime: .zero)

let colorSpace = CGColorSpaceCreateDeviceRGB()
let ink = CGColor(colorSpace: colorSpace, components: [0.12, 0.12, 0.16, 1])!

func drawFigure(_ ctx: CGContext, x: Double, phase: Double, scale: Double) {
    let groundY = Double(height) - 40.0
    let hipY = groundY - 80.0 * scale
    let headR = 11.0 * scale

    ctx.setStrokeColor(ink)
    ctx.setFillColor(ink)
    ctx.setLineWidth(5.0 * scale)
    ctx.setLineCap(.round)

    ctx.fillEllipse(in: CGRect(x: x - headR, y: hipY + 62 * scale - headR,
                               width: headR * 2, height: headR * 2))
    ctx.move(to: CGPoint(x: x, y: hipY + 52 * scale))
    ctx.addLine(to: CGPoint(x: x, y: hipY))
    ctx.strokePath()

    // Side-on shows a big leg excursion; front-on shows mostly lateral separation.
    let swing = sin(phase) * (mode == "sagittal" ? 26.0 : 12.0) * scale
    for side in [1.0, -1.0] {
        let footX = x + swing * side
        let kneeX = x + swing * side * 0.5
        let kneeY = hipY - 40 * scale + abs(swing) * 0.15
        ctx.move(to: CGPoint(x: x, y: hipY))
        ctx.addLine(to: CGPoint(x: kneeX, y: kneeY))
        ctx.addLine(to: CGPoint(x: footX, y: groundY))
        ctx.strokePath()
    }

    let armSwing = -sin(phase) * 18.0 * scale
    for side in [1.0, -1.0] {
        ctx.move(to: CGPoint(x: x, y: hipY + 46 * scale))
        ctx.addLine(to: CGPoint(x: x + armSwing * side, y: hipY + 14 * scale))
        ctx.strokePath()
    }
}

var frameIndex = 0
while frameIndex < totalFrames {
    if !input.isReadyForMoreMediaData {
        usleep(2000)
        continue
    }

    var pixelBuffer: CVPixelBuffer?
    CVPixelBufferPoolCreatePixelBuffer(nil, adaptor.pixelBufferPool!, &pixelBuffer)
    guard let buffer = pixelBuffer else { break }

    CVPixelBufferLockBaseAddress(buffer, [])
    let ctx = CGContext(
        data: CVPixelBufferGetBaseAddress(buffer),
        width: width, height: height,
        bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue
    )!

    ctx.setFillColor(CGColor(colorSpace: colorSpace, components: [0.88, 0.89, 0.91, 1])!)
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    ctx.setFillColor(CGColor(colorSpace: colorSpace, components: [0.72, 0.73, 0.76, 1])!)
    ctx.fill(CGRect(x: 0, y: 0, width: width, height: 40))
    ctx.setStrokeColor(CGColor(colorSpace: colorSpace, components: [0.6, 0.61, 0.64, 1])!)
    ctx.setLineWidth(2)
    for markX in stride(from: 0, to: width, by: 64) {
        ctx.move(to: CGPoint(x: Double(markX), y: 36))
        ctx.addLine(to: CGPoint(x: Double(markX), y: 44))
    }
    ctx.strokePath()

    let t = Double(frameIndex) / Double(fps)
    let progress = t / seconds

    if mode == "sagittal" {
        // Crosses the frame left to right at constant size.
        drawFigure(ctx, x: progress * Double(width), phase: t * 7.0, scale: 1.0)
    } else {
        // Approaches down the middle, growing as it nears the camera.
        drawFigure(ctx, x: Double(width) / 2, phase: t * 7.0, scale: 0.55 + progress * 0.85)
    }

    CVPixelBufferUnlockBaseAddress(buffer, [])
    adaptor.append(buffer, withPresentationTime: CMTime(value: CMTimeValue(frameIndex), timescale: fps))
    frameIndex += 1
}

input.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
done.wait()

if writer.status == .completed {
    print(String(format: "wrote %@: %@, %.1fs", outPath, mode, seconds))
} else {
    print("failed: \(String(describing: writer.error))")
    exit(1)
}
