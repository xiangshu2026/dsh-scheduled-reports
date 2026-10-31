@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   DSH Plugin Weekly Digest
echo ================================================
python run_weekly.py %*
echo.
echo Reports: %~dp0reports
echo.
pause
