@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo Prism needs Node.js 20 or newer. Install it from https://nodejs.org and try again.
  echo.
  pause
  exit /b 1
)
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Milliseconds 900; Start-Process 'http://127.0.0.1:4173'"
node server.mjs
if errorlevel 1 pause
