@echo off
rem Double-clic : installe (ou met à jour) Manhwa Studio. Détail : install\install.ps1
chcp 65001 >nul
cd /d "%~dp0"
title Manhwa Studio : installation
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\install.ps1" %*
echo.
pause
