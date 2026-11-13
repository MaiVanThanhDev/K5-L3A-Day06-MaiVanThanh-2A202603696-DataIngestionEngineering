@echo off
cd /d "%~dp0"
echo LAB6 UI: http://127.0.0.1:8765
echo Keep this window open. Press Ctrl+C to stop.
python ui/server.py
if errorlevel 1 pause
