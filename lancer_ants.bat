@echo off
cd /d "%~dp0"
py ants.py 2>nul || python ants.py
pause
