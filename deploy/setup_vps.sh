#!/bin/bash
set -e

echo "=========================================================="
echo " AURUM Institutional 24/7 Cloud Engine — Turnkey VPS Setup"
echo "=========================================================="

# 1. Update OS
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl wget git ufw

# 2. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "[STEP 1/4] Installing Docker Engine..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
fi

# 3. Setup Firewall (UFW)
echo "[STEP 2/4] Configuring UFW Firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 6080/tcp  # noVNC Browser GUI
sudo ufw allow 8501/tcp  # Streamlit
sudo ufw --force enable || true

# 4. Clone or update repository
echo "[STEP 3/4] Preparing AURUM Repository..."
APP_DIR="$HOME/aurum_research"
if [ ! -d "$APP_DIR" ]; then
    git clone https://github.com/learningdata0/aurum_research.git "$APP_DIR"
fi

cd "$APP_DIR"
git pull origin main

# 5. Launch Containerized MT5 + Shadow Daemon
echo "[STEP 4/4] Building and Launching 24/7 Cloud Engine..."
docker compose build
docker compose up -d

SERVER_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "=========================================================="
echo "✅ AURUM 24/7 CLOUD ENGINE IS DEPLOYED AND RUNNING!"
echo "=========================================================="
echo "• Web Browser MT5 Interface: http://${SERVER_IP}:6080/vnc.html"
echo "• Streamlit Cloud Dashboard: https://aurumresearch-jgzbuwgauapd4mtnfxbm6d.streamlit.app/"
echo "• Telegram Real-Time Alerts: Active via @shadow2030bot"
echo "=========================================================="
