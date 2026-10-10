#!/usr/bin/env bash
# ==============================================================================
# AURUM Institutional Desk - Linux Launcher
# ==============================================================================

MODE=${1:-web}

if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment .venv not found. Run ./setup_linux.sh first."
    exit 1
fi

source .venv/bin/activate
export PYTHONPATH=.

if [ "$MODE" == "web" ]; then
    echo "🚀 Launching AURUM Institutional Streamlit Web Desk on port 8501..."
    streamlit run app.py --server.port 8501 --server.address 0.0.0.0
elif [ "$MODE" == "sentinel" ]; then
    echo "🛡️ Launching AURUM 24/7 Sentinel Shadow Trading Daemon..."
    python3 -m src.shadow_daemon --mode watch --interval 1
elif [ "$MODE" == "test" ]; then
    echo "🔬 Running Full Institutional Test Suite..."
    pytest -v
else
    echo "Usage: ./run_linux.sh [web|sentinel|test]"
fi
