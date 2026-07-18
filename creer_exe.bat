@echo off
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller
py -m PyInstaller --noconfirm --clean --onefile --windowed --name ANTs ants.py
echo.
echo L'executable se trouve dans le dossier dist.
pause
