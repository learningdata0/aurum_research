#!/bin/bash
set -e

echo "=== AURUM Institutional 24/7 Cloud Engine Initialization ==="

export DISPLAY=:1
export WINEPREFIX=/root/.wine
export WINEARCH=win64
export WINEDLLOVERRIDES="mscoree,mshtml="

# 1. Start Xvfb first so all Wine commands have a valid X11 Display
echo "[INIT] Starting Xvfb on display :1..."
Xvfb :1 -screen 0 1920x1080x24 &
XVFB_PID=$!
sleep 2

# 2. Initialize Wine prefix if needed (non-interactive)
if [ ! -d "/root/.wine/drive_c/windows" ]; then
    echo "[INIT] Creating 64-bit Wine prefix..."
    wineboot -u || true
    sleep 3
fi

# 3. Setup MT5 directories
MT5_BASE="/root/.wine/drive_c/Program Files/MetaTrader 5"
ADVISORS_DIR="$MT5_BASE/MQL5/Experts/Advisors"
mkdir -p "$ADVISORS_DIR"
mkdir -p "$MT5_BASE/MQL5/Files"

# 4. Copy our EAs into MT5 Advisors directory
if [ -d "/app/src/mql5" ]; then
    echo "[INIT] Deploying compiled AURUM EAs..."
    cp /app/src/mql5/*.mq5 "$ADVISORS_DIR/" 2>/dev/null || true
    cp /app/src/mql5/*.ex5 "$ADVISORS_DIR/" 2>/dev/null || true
fi

# 5. If terminal64.exe is missing, download installer
if [ ! -f "$MT5_BASE/terminal64.exe" ]; then
    echo "[INIT] Downloading MetaTrader 5 setup..."
    wget -q -O /tmp/mt5setup.exe https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
    echo "[INIT] Installing MT5 into Wine prefix (headless)..."
    wine /tmp/mt5setup.exe /auto || true
    sleep 8
fi

# Stop temporary Xvfb before supervisord starts its own managed Xvfb
kill $XVFB_PID 2>/dev/null || true
sleep 1

echo "[INIT] Starting Supervisor (Xvfb + noVNC + MT5 + Shadow Daemon)..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf

