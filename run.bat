@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0dist\AutoClickerPro.exe" (
    start "" "%~dp0dist\AutoClickerPro.exe"
) else (
    where py >nul 2>nul && (start "" py -3 "%~dp0auto_clicker.py" & exit /b)
    start "" pythonw "%~dp0auto_clicker.py"
)
