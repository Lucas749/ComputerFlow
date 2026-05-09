// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "ComputerFlow",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "ComputerFlow",
            path: "ComputerFlow",
            exclude: [
                "Info.plist",
                "ComputerFlow.entitlements",
                "BundleInfo.plist",
                "Assets.xcassets"
            ],
            linkerSettings: [
                .linkedFramework("Carbon"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("ScreenCaptureKit"),
                .linkedFramework("WebKit"),
                .linkedFramework("UniformTypeIdentifiers")
            ]
        )
    ]
)
