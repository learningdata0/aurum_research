#!/bin/bash
set -e

echo "=== AURUM Institutional 24/7 Cloud Engine Initialization ==="

# 1. Initialize Wine prefix if needed
if [ ! -d "/root/.wine/drive_c" ]; then
    echo "[INIT] Creating 64-bit Wine prefix..."
    wineboot --init
    sleep 3
fi

# 2. Setup MT5 directories
MT5_BASE="/root/.wine/drive_c/Program Files/MetaTrader 5"
ADVISORS_DIR="$MT5_BASE/MQL5/Experts/Advisors"
mkdir -p "$ADVISORS_DIR"
mkdir -p "$MT5_BASE/MQL5/Files"

# 3. Copy our EAs into MT5 Advisors directory
if [ -d "/app/src/mql5" ]; then
    echo "[INIT] Deploying compiled AURUM EAs..."
    cp /app/src/mql5/*.mq5 "$ADVISORS_DIR/" 2>/dev/null || true
    cp /app/src/mql5/*.ex5 "$ADVISORS_DIR/" 2>/dev/null || true
fi

# 4. If terminal64.exe is missing, download installer
if [ ! -f "$MT5_BASE/terminal64.exe" ]; then
    echo "[INIT] Downloading MetaTrader 5 setup..."
    wget -O /tmp/mt5setup.exe https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
    echo "[INIT] Installing MT5 into Wine prefix (headless)..."
    wine /tmp/mt5setup.exe /auto
    sleep 10
fi

echo "[INIT] Starting Supervisor (Xvfb + noVNC + MT5 + Shadow Daemon)..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
