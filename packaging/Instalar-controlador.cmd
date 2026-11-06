@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Driver.ps1" -Install
pause
