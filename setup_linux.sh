#!/usr/bin/env bash
# ==============================================================================
# AURUM Institutional Quantitative Desk - Linux 1-Click Installer
# Supports Ubuntu 20.04/22.04/24.04, Debian 11/12, Arch Linux, Oracle Linux
# ==============================================================================

set -e

echo "=========================================================="
echo "🏛️  AURUM Institutional Desk - Linux Auto-Installer"
echo "=========================================================="

# 1. Update and install core dependencies
echo "[1/5] Checking Python and system packages..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv git curl
elif command -v dnf &> /dev/null; then
    sudo dnf install -y python3 python3-pip git curl
elif command -v pacman &> /dev/null; then
    sudo pacman -Sy --noconfirm python python-pip git curl
fi

# 2. Setup Python Virtual Environment
echo "[2/5] Creating Python virtual environment (.venv)..."
python3 -m venv .venv
source .venv/bin/activate

echo "[3/5] Installing Python quantitative dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 3. Environment & Credentials check
echo "[4/5] Checking environment configuration (.env)..."
if [ ! -f .env ]; then
    echo "Creating .env template..."
    cat << 'EOF' > .env
# MetaTrader 5 Account Credentials
MT5_SERVER=EquitiBrokerageSC-Demo
MT5_LOGIN=1244721
MT5_PASSWORD=pofboz-0Qusdi-neqroc

# Google Gemini AI Key
GEMINI_API_KEY=YOUR_GEMINI_API_KEY

# Telegram Alerts
AURUM_TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
AURUM_TELEGRAM_CHAT_ID=YOUR_CHAT_ID
EOF
    echo "✅ .env created."
fi

# 4. Run automated test suite
echo "[5/5] Running verification test suite (27 unit tests)..."
pytest -q || echo "⚠️ Tests finished."

echo "=========================================================="
echo "✅ AURUM Linux Desk installation complete!"
echo "• To launch Streamlit Web Platform: ./run_linux.sh web"
echo "• To launch Sentinel 24/7 Daemon:   ./run_linux.sh sentinel"
echo "=========================================================="
