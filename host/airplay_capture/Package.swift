// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AirPlayCapture",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "airplay-capture", targets: ["AirPlayCapture"])],
    targets: [.executableTarget(name: "AirPlayCapture")]
)
