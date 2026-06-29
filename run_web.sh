#!/bin/bash

# Move to the directory containing this script
cd "$(dirname "$0")"

echo "=========================================================="
echo "🚀 Tech Watch Tracker Web Server Bootloader"
echo "=========================================================="

# 1. Locate python binary
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "[1/4] Checking python interpreter..."
echo "Using python: $($PYTHON_BIN -c 'import sys; print(sys.executable)')"
echo "Python version: $($PYTHON_BIN --version)"

# 2. Check and install dependencies
echo ""
echo "[2/4] Verifying python dependencies (FastAPI, Uvicorn, BeautifulSoup, certifi)..."
$PYTHON_BIN -c "import fastapi, uvicorn, bs4, certifi" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Dependencies missing. Installing required packages..."
    $PYTHON_BIN -m pip install fastapi uvicorn beautifulsoup4 certifi
    if [ $? -ne 0 ]; then
        echo "❌ Error installing dependencies. Make sure pip is installed."
        exit 1
    fi
    echo "✅ Dependencies installed successfully."
else
    echo "✅ Dependencies verified (fastapi, uvicorn found)."
fi

# 3. Fetch local IP address for team sharing
echo ""
echo "[3/4] Fetching local IP address for sharing with team members..."
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)

echo "----------------------------------------------------------"
echo "👉 Local Access URL (본인 기기 접속용):"
echo "   http://localhost:8000"
echo ""
if [ ! -z "$LOCAL_IP" ]; then
    echo "👉 Team Shared Access URL (팀원 공유용 주소):"
    echo "   http://$LOCAL_IP:8000"
else
    echo "⚠️ Local network IP could not be auto-detected."
    echo "Please find your computer's local IP address using Network settings."
fi
echo "----------------------------------------------------------"

# 4. Check Apple Silicon Mac ARM64 Native execution
echo "[4/4] Starting FastAPI Web Server..."
IS_ARM64=0
SYSCTL_VAL=$(sysctl -n hw.optional.arm64 2>/dev/null)
if [ "$SYSCTL_VAL" = "1" ]; then
    IS_ARM64=1
fi

if [ $IS_ARM64 -eq 1 ]; then
    echo "Detected Apple Silicon Mac. Running web server natively (arm64)..."
    exec arch -arm64 $PYTHON_BIN web_server.py
else
    exec $PYTHON_BIN web_server.py
fi
