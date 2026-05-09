#!/usr/bin/env bash
# Build ComputerFlow.app from Swift sources using swift build (no Xcode required).
# Usage:  ./scripts/build_mac.sh
# Output: build/ComputerFlow.app  (ready to run, ad-hoc signed)

set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

APP_NAME="ComputerFlow"
BUNDLE="$ROOT/build/$APP_NAME.app"
MAC_PKG="$ROOT/mac"

echo "▶ Building $APP_NAME …"
cd "$MAC_PKG"
swift build -c release 2>&1

# Locate the compiled binary (path varies by arch)
BIN=$(find "$MAC_PKG/.build" -name "$APP_NAME" -type f | grep release | head -1)
if [ -z "$BIN" ]; then
    echo "❌ Binary not found after build"; exit 1
fi
echo "   Binary: $BIN"

echo "▶ Assembling .app bundle …"
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS"
mkdir -p "$BUNDLE/Contents/Resources"

cp "$BIN"                              "$BUNDLE/Contents/MacOS/$APP_NAME"
cp "$MAC_PKG/$APP_NAME/BundleInfo.plist" "$BUNDLE/Contents/Info.plist"

# Copy assets if they exist
ASSETS="$MAC_PKG/$APP_NAME/Assets.xcassets"
if [ -d "$ASSETS" ]; then
    xcrun actool "$ASSETS" \
        --compile "$BUNDLE/Contents/Resources" \
        --platform macosx \
        --minimum-deployment-target 14.0 \
        --app-icon AppIcon \
        --output-partial-info-plist /dev/null 2>/dev/null || true
fi

echo "▶ Code-signing (ad-hoc + entitlements) …"
codesign \
    --force \
    --deep \
    --sign - \
    --entitlements "$MAC_PKG/$APP_NAME/ComputerFlow.entitlements" \
    --options runtime \
    "$BUNDLE"

echo ""
echo "✅  Done →  $BUNDLE"
echo ""
echo "   To run:"
echo "   open $BUNDLE"
echo ""
echo "   First launch: macOS will prompt for Screen Recording permission."
echo "   Grant it in System Settings → Privacy & Security → Screen Recording."
