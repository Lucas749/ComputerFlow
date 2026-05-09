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

# Generate AppIcon.icns from PNG assets using Python
ICONSET="$MAC_PKG/$APP_NAME/Assets.xcassets/AppIcon.appiconset"
ICNS_OUT="$BUNDLE/Contents/Resources/AppIcon.icns"
if [ -f "$ICONSET/icon_512x512.png" ]; then
    python3 - <<PYEOF
import struct, os
from PIL import Image

iconset = "$ICONSET"
out = "$ICNS_OUT"

SIZES = [
    (16,   b'icp4'),
    (32,   b'icp5'),
    (64,   b'icp6'),
    (128,  b'ic07'),
    (256,  b'ic08'),
    (512,  b'ic09'),
    (1024, b'ic10'),
]

def png_bytes(size):
    p = f"{iconset}/icon_{size}x{size}.png"
    if not os.path.exists(p):
        p = f"{iconset}/icon_512x512@2x.png"
    with open(p, 'rb') as f:
        return f.read()

chunks = []
for size, ostype in SIZES:
    data = png_bytes(size)
    chunks.append(ostype + struct.pack('>I', 8 + len(data)) + data)

body = b''.join(chunks)
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'wb') as f:
    f.write(b'icns' + struct.pack('>I', 8 + len(body)) + body)
print(f"   AppIcon.icns written ({len(body)} bytes)")
PYEOF
fi

echo "▶ Code-signing (ad-hoc + entitlements) …"
codesign \
    --force \
    --deep \
    --sign - \
    --entitlements "$MAC_PKG/$APP_NAME/ComputerFlow.entitlements" \
    --options runtime \
    "$BUNDLE"

echo "▶ Installing to /Applications …"
INSTALLED="/Applications/$APP_NAME.app"
if [ -d "$INSTALLED" ]; then
    # Update in-place so macOS TCC keeps the existing permission grants
    cp "$BUNDLE/Contents/MacOS/$APP_NAME"    "$INSTALLED/Contents/MacOS/$APP_NAME"
    cp "$BUNDLE/Contents/Info.plist"          "$INSTALLED/Contents/Info.plist"
    cp "$BUNDLE/Contents/Resources/AppIcon.icns" "$INSTALLED/Contents/Resources/AppIcon.icns" 2>/dev/null || true
    # Re-sign the updated bundle in-place
    codesign --force --deep --sign - \
        --entitlements "$MAC_PKG/$APP_NAME/ComputerFlow.entitlements" \
        --options runtime \
        "$INSTALLED"
else
    # First install — full copy
    cp -R "$BUNDLE" "$INSTALLED"
fi
touch "$INSTALLED"

echo "▶ Restarting $APP_NAME …"
pkill -x "$APP_NAME" 2>/dev/null || true
sleep 0.4

# Ad-hoc builds get a new binary hash each time, so TCC forgets permissions.
# Reset both entries so macOS re-prompts cleanly on next launch.
tccutil reset ScreenCapture com.computerflow.app 2>/dev/null || true
tccutil reset Accessibility com.computerflow.app 2>/dev/null || true

open "/Applications/$APP_NAME.app"

# Give the app a moment to launch, then open System Settings to the right pane
# so you can re-grant Screen Recording and Accessibility in one step.
sleep 1.5
echo "▶ Opening Privacy settings — re-grant Screen Recording + Accessibility …"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"

echo ""
echo "✅  Done →  $BUNDLE"
echo "           /Applications/$APP_NAME.app"
echo ""
echo "   To run:"
echo "   open /Applications/$APP_NAME.app"
echo ""
echo "   First launch: macOS will prompt for Screen Recording permission."
echo "   Grant it in System Settings → Privacy & Security → Screen Recording."
