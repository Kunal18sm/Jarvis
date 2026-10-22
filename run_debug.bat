@echo off
title JARVIS (Debug Mode with Console)
cd /d "%~dp0"
echo ========================================================
echo Starting JARVIS in DEBUG mode (Console output enabled)
echo ========================================================
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)
pause
