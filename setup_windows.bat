@echo off
REM ==============================================================================
REM AURUM Institutional Quantitative Desk - Windows 1-Click Installer
REM Supports Windows 10 & Windows 11 (64-bit)
REM ==============================================================================

echo ==========================================================
echo [AURUM] Institutional Quantitative Desk - Windows Installer
echo ==========================================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ is not found in PATH!
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/4] Creating Python Virtual Environment (.venv)...
if not exist .venv (
    python -m venv .venv
)

echo [2/4] Activating .venv and installing quantitative dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/4] Setting up .env configuration...
if not exist .env (
    (
        echo # MetaTrader 5 Account Credentials
        echo MT5_SERVER=EquitiBrokerageSC-Demo
        echo MT5_LOGIN=1244721
        echo MT5_PASSWORD=pofboz-0Qusdi-neqroc
        echo.
        echo # Google Gemini AI Key
        echo GEMINI_API_KEY=YOUR_GEMINI_API_KEY
        echo.
        echo # Telegram Alerts
        echo AURUM_TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
        echo AURUM_TELEGRAM_CHAT_ID=YOUR_CHAT_ID
    ) > .env
    echo [OK] Created .env file.
)

echo [4/4] Verifying unit test suite...
pytest -q

echo.
echo ==========================================================
echo [SUCCESS] AURUM Windows Desk Installation Complete!
echo.
echo • Double-click "run_streamlit.bat" to open the Web Dashboard.
echo • Double-click "run_sentinel.bat" to run the 24/7 Trading Sentinel.
echo ==========================================================
echo.
pause
