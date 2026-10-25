#!/bin/bash
set -e

APP_NAME="Audio Fixer"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_BUNDLE="$PROJECT_DIR/$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
APP_DIR="$RESOURCES/app"

echo "=== Building $APP_NAME.app ==="

# Clean old bundle
rm -rf "$APP_BUNDLE"

# Create directory structure
mkdir -p "$MACOS"
mkdir -p "$RESOURCES"
mkdir -p "$APP_DIR"

# Copy code into Resources/app
cp "$PROJECT_DIR/audio_fixer.py" "$APP_DIR/"
cp "$PROJECT_DIR/gui.py" "$APP_DIR/"
cp "$PROJECT_DIR/requirements.txt" "$APP_DIR/"
cp -R "$PROJECT_DIR/core" "$APP_DIR/"

# Copy icon if available
if [ -f "/tmp/AppIcon.icns" ]; then
    cp "/tmp/AppIcon.icns" "$RESOURCES/AppIcon.icns"
fi

# Create Info.plist
cat << 'EOF' > "$CONTENTS/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Audio Fixer</string>
    <key>CFBundleExecutable</key>
    <string>Audio Fixer</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.jimbrouwer.audiofixer</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Audio Fixer</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>
            <string>Audio Files &amp; Folders</string>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
            <key>LSHandlerRank</key>
            <string>Alternate</string>
            <key>LSItemContentTypes</key>
            <array>
                <string>com.microsoft.waveform-audio</string>
                <string>public.audio</string>
                <string>public.folder</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
EOF

# Create executable launcher
cat << 'EOF' > "$MACOS/Audio Fixer"
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources/app" && pwd)"

# Discover python3
if [ -x "/usr/local/bin/python3" ]; then
    PYTHON="/usr/local/bin/python3"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON="/opt/homebrew/bin/python3"
elif [ -x "/usr/bin/python3" ]; then
    PYTHON="/usr/bin/python3"
else
    PYTHON="$(which python3)"
fi

export PYTHONPATH="$DIR:$PYTHONPATH"
cd "$DIR"
exec "$PYTHON" "$DIR/gui.py" "$@"
EOF

chmod +x "$MACOS/Audio Fixer"

echo "=== Successfully built $APP_BUNDLE ==="
