@echo off
rem Double-clic : lance le Studio et l'ouvre dans le navigateur.
rem Fermer cette fenêtre arrête le Studio.
chcp 65001 >nul
cd /d "%~dp0"
title Manhwa Studio
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
    echo L'environnement Python est introuvable : installe d'abord le projet ^(voir README^).
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m manhwa studio
if errorlevel 1 pause
