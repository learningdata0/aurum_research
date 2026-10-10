@echo off
title AURUM Institutional Web Platform
cd /d %~dp0
call .venv\Scripts\activate.bat
set PYTHONPATH=.
echo ==========================================================
echo Starting AURUM Quantitative Terminal on http://localhost:8501
echo ==========================================================
streamlit run app.py
pause
