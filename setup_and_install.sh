#!/bin/bash

# Setup and Installation script for Tech Watch Assistant
# Registers the Python script as a macOS background LaunchAgent daemon.

echo "=============================================="
echo "Installing Tech Watch Assistant Daemon..."
echo "=============================================="

# 1. Check Python installation
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "ERROR: python3 not found. Please install Python 3 on your Mac."
    exit 1
fi
echo "Using python3 located at: $PYTHON_PATH"

# Get current script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
echo "Project directory: $DIR"

# 2. Check dependencies (install google-antigravity package if needed)
echo "Checking Python package dependencies..."
$PYTHON_PATH -c "import google.antigravity" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing google-antigravity package..."
    $PYTHON_PATH -m pip install google-antigravity
    if [ $? -ne 0 ]; then
        echo "Failed to install google-antigravity automatically. Trying user space install..."
        $PYTHON_PATH -m pip install --user google-antigravity
    fi
else
    echo "google-antigravity is already installed."
fi

# 3. Create LaunchAgent plist file
PLIST_PATH="$HOME/Library/LaunchAgents/com.user.techwatchassistant.plist"
echo "Creating LaunchAgent configuration at: $PLIST_PATH"

cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.techwatchassistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$DIR/agent.py</string>
    </array>
    <key>StartInterval</key>
    <integer>21600</integer> <!-- Run every 6 hours (21600 seconds) -->
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$DIR/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/agent.err</string>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
</dict>
</plist>
EOF

# 4. Register and Load the Daemon
echo "Registering with macOS background services..."
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

if [ $? -eq 0 ]; then
    echo "SUCCESS: Tech Watch Assistant registered successfully!"
    echo "It will run in the background every 6 hours."
    echo "To view logs, you can open:"
    echo " - $DIR/agent.log"
    echo " - $DIR/agent.err"
else
    echo "WARNING: Failed to load plist into launchctl. Try running: launchctl load $PLIST_PATH manually."
fi

# 5. Compile and install Desktop Application
echo "Compiling native macOS Desktop Application..."
bash "$DIR/build_app.sh"

# 6. Run Initial Test
echo ""
echo "=============================================="
echo "Running initial test scan..."
echo "=============================================="
echo "Note: macOS may prompt you for permission to let Terminal control Apple Notes."
echo "Please click 'OK' or 'Allow' when the prompt appears."
echo "----------------------------------------------"

$PYTHON_PATH "$DIR/agent.py"

echo "----------------------------------------------"
echo "Initial test completed. Check your Apple Notes (folders: Tech Watch - Docs / Trends) and your Discord channel!"
echo "You can double-click 'Tech Watch Tracker' on your Desktop to open the Control Panel."
echo "=============================================="
