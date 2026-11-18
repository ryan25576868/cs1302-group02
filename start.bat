@echo off
cd /d "%~dp0"
start "" http://127.0.0.1:4173
python python_app\server.py --port 4173
