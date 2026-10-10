@echo off
title AURUM 24/7 Trading Sentinel Daemon
cd /d %~dp0
call .venv\Scripts\activate.bat
set PYTHONPATH=.
echo ==========================================================
echo Starting AURUM 24/7 Trading Sentinel with Telegram & Gemini AI...
echo ==========================================================
python -m src.shadow_daemon --mode watch --interval 1
pause
