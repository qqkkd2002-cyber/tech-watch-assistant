#!/bin/bash

# Build Script to compile the Tech Watch Assistant into a macOS .app Bundle with custom icon

echo "=============================================="
echo "Creating clickable macOS Application (.app)..."
echo "=============================================="

PROJECT_DIR="/Users/parkjongho/.gemini/antigravity/scratch/tech-watch-assistant"
APP_NAME="Tech Watch Tracker"
APP_DIR="$PROJECT_DIR/$APP_NAME.app"

# Clean previous app build
rm -rf "$APP_DIR"

# 1. Create directory structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# 2. Find Python Binary
PYTHON_BIN=$(which python3)
if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="/usr/bin/python3"
fi

# 3. Create the executable launcher script
LAUNCHER_PATH="$APP_DIR/Contents/MacOS/app_launcher"
cat <<EOF > "$LAUNCHER_PATH"
#!/bin/bash
cd "$PROJECT_DIR"
# Force native Apple Silicon execution if hardware is ARM64 to prevent Rosetta clashes
if [ "\$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then
    exec arch -arm64 "$PYTHON_BIN" gui.py
else
    exec "$PYTHON_BIN" gui.py
fi
EOF

# Make launcher executable
chmod +x "$LAUNCHER_PATH"

# 4. Create Info.plist
PLIST_PATH="$APP_DIR/Contents/Info.plist"
cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>app_launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.user.techwatchtracker.arm</string>
    <key>CFBundleName</key>
    <string>Tech Watch Tracker</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# 5. Compile PNG to macOS native .icns file
PNG_ICON="/Users/parkjongho/.gemini/antigravity/brain/c279bb51-e077-4b2f-a21e-ae44bd6adf60/tech_watch_icon_1780043456486.png"
ICNS_PATH="$APP_DIR/Contents/Resources/AppIcon.icns"

if [ -f "$PNG_ICON" ]; then
    echo "Compiling PNG to macOS native .icns..."
    ICONSET_DIR="$PROJECT_DIR/TechWatch.iconset"
    mkdir -p "$ICONSET_DIR"
    
    # Generate icons matching Apple specifications using sips (forcing PNG format conversion)
    sips -s format png -z 16 16     "$PNG_ICON" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null 2>&1
    sips -s format png -z 32 32     "$PNG_ICON" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null 2>&1
    sips -s format png -z 32 32     "$PNG_ICON" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null 2>&1
    sips -s format png -z 64 64     "$PNG_ICON" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null 2>&1
    sips -s format png -z 128 128   "$PNG_ICON" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null 2>&1
    sips -s format png -z 256 256   "$PNG_ICON" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null 2>&1
    sips -s format png -z 256 256   "$PNG_ICON" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null 2>&1
    sips -s format png -z 512 512   "$PNG_ICON" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null 2>&1
    sips -s format png -z 512 512   "$PNG_ICON" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null 2>&1
    sips -s format png -z 1024 1024 "$PNG_ICON" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null 2>&1
    
    # Pack iconset to .icns
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"
    
    # Clean temporary iconset
    rm -rf "$ICONSET_DIR"
    echo "Custom icon packed successfully."
else
    # Fallback to copy toolbar util icon if PNG is missing
    echo "Warning: PNG Icon not found. Using system fallback icon."
    SYSTEM_ICON="/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/ToolbarUtilitiesFolderIcon.icns"
    if [ -f "$SYSTEM_ICON" ]; then
        cp "$SYSTEM_ICON" "$ICNS_PATH"
    fi
fi

# 6. Copy App Bundle to User's Desktop
DESKTOP_DIR="/Users/parkjongho/Desktop"
DESKTOP_APP="$DESKTOP_DIR/$APP_NAME.app"

echo "Copying application to Desktop..."
rm -rf "$DESKTOP_APP"
cp -R "$APP_DIR" "$DESKTOP_APP"

# Unquarantine the app
xattr -d com.apple.quarantine "$DESKTOP_APP" 2>/dev/null
xattr -cr "$DESKTOP_APP" 2>/dev/null

# Force Finder to refresh its icon cache immediately
touch "$DESKTOP_APP"

echo "=============================================="
echo "SUCCESS: '$APP_NAME' application is created!"
echo "It has been copied to your Desktop: $DESKTOP_APP"
echo "You can double-click it to start the dashboard!"
echo "=============================================="
