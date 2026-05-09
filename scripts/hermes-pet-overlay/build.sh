#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p ../../build

app_dir="../../build/HermesPetOverlay.app"
macos_dir="$app_dir/Contents/MacOS"
resources_dir="$app_dir/Contents/Resources/koda"
mkdir -p "$macos_dir"
mkdir -p "$resources_dir"

clang HermesPetOverlay.m \
  -fobjc-arc \
  -framework Cocoa \
  -framework ApplicationServices \
  -framework ScreenCaptureKit \
  -framework CoreMedia \
  -o "$macos_dir/hermes-pet-overlay"

asset_dir="../../hermes-agent-pets/hermes-pet-agent/assets/koda"
if [[ -d "$asset_dir" ]]; then
  cp "$asset_dir"/*.png "$resources_dir"/ 2>/dev/null || true
  cp "$asset_dir"/*.webp "$resources_dir"/ 2>/dev/null || true
  cp "$asset_dir"/*.json "$resources_dir"/ 2>/dev/null || true
fi

cat > "$app_dir/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>hermes-pet-overlay</string>
  <key>CFBundleIdentifier</key>
  <string>local.hermes.pet.overlay</string>
  <key>CFBundleName</key>
  <string>Hermes Pet Overlay</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSBackgroundOnly</key>
  <false/>
  <key>LSUIElement</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

echo "$app_dir"
