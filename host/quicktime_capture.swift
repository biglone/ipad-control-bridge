import CoreGraphics
import Foundation

let output = CommandLine.arguments.dropFirst().first ?? "current.jpg"

func findQuickTimeWindow() -> CGWindowID? {
    guard let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else {
        return nil
    }
    for window in list {
        let owner = (window[kCGWindowOwnerName as String] as? String ?? "").lowercased()
        let title = (window[kCGWindowName as String] as? String ?? "").lowercased()
        if owner.contains("quicktime") || title.contains("movie recording") || title.contains("录影") {
            return window[kCGWindowNumber as String] as? CGWindowID
        }
    }
    return nil
}

while true {
    if let windowID = findQuickTimeWindow() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
        process.arguments = ["-x", "-t", "jpg", "-l", String(windowID), output]
        try? process.run()
        process.waitUntilExit()
    } else {
        fputs("Waiting for a QuickTime movie recording window...\n", stderr)
        sleep(1)
    }
    usleep(250_000)
}
