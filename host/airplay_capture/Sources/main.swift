import CoreImage
import CoreMedia
import Foundation
import AppKit
import ScreenCaptureKit

final class CaptureDelegate: NSObject, SCStreamOutput, SCStreamDelegate {
    private let context = CIContext()
    private let outputURL: URL
    private var lastWrite = Date.distantPast

    init(outputURL: URL) { self.outputURL = outputURL }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let now = Date()
        guard now.timeIntervalSince(lastWrite) >= 0.12 else { return }
        lastWrite = now
        let image = CIImage(cvPixelBuffer: imageBuffer)
        guard let data = context.jpegRepresentation(of: image, colorSpace: CGColorSpaceCreateDeviceRGB(), options: [:]) else { return }
        try? data.write(to: outputURL, options: Data.WritingOptions.atomic)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fputs("AirPlay capture stopped: \(error)\n", stderr)
        exit(1)
    }
}

@main
struct AirPlayCapture {
    static func main() async throws {
        // Initialize the macOS GUI session before querying window content.
        _ = NSApplication.shared
        let outputURL = URL(fileURLWithPath: CommandLine.arguments.dropFirst().first ?? "current.jpg")
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        let candidates = content.windows.filter { window in
            let title = (window.title ?? "").lowercased()
            let owner = window.owningApplication?.applicationName.lowercased() ?? ""
            return title.contains("ipad") || title.contains("airplay") || owner.contains("airplay")
                || owner.contains("quicktime") || title.contains("movie recording")
        }
        guard let window = candidates.first else {
            let names = content.windows.map { "\($0.owningApplication?.applicationName ?? "?") / \($0.title ?? "")" }.joined(separator: "\n")
            fputs("No AirPlay/iPad window found. Visible windows:\n\(names)\n", stderr)
            exit(2)
        }

        let filter = SCContentFilter(desktopIndependentWindow: window)
        let config = SCStreamConfiguration()
        config.width = max(640, Int(window.frame.width))
        config.height = max(480, Int(window.frame.height))
        config.minimumFrameInterval = CMTime(value: 1, timescale: 10)
        config.queueDepth = 3
        config.pixelFormat = kCVPixelFormatType_32BGRA

        let delegate = CaptureDelegate(outputURL: outputURL)
        let stream = SCStream(filter: filter, configuration: config, delegate: delegate)
        try stream.addStreamOutput(delegate, type: SCStreamOutputType.screen, sampleHandlerQueue: DispatchQueue(label: "airplay.capture"))
        try await stream.startCapture()
        print("Capturing \(window.title ?? "Untitled") → \(outputURL.path)")
        dispatchMain()
    }
}
