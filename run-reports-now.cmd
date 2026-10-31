REM DSH Scheduled Reports - unattended report generation and archiving
REM https://github.com/xiangshu2026/dsh-scheduled-reports
@echo off
setlocal

rem ============================================================
rem  DSH report generator -- RUNS ON DEMAND ONLY
rem
rem  There is no longer any automatic schedule. Double-click the
rem  desktop shortcut whenever you want fresh reports; nothing
rem  runs in the background otherwise.
rem
rem  This DOES call the model (3 tasks) and uses credit.
rem  It takes roughly 5-6 minutes.
rem
rem  Keep this file ASCII-only: cmd.exe parses batch files by byte
rem  offset and non-ASCII text corrupts the parsing of later lines.
rem ============================================================

set "PIPELINE=%~dp0run-daily-task.cmd"
set "LOGDIR=%~dp0logs"
set "OUTDIR=%USERPROFILE%\Desktop\DSH-Reports"

echo.
echo ============================================================
echo   DSH  report generator   (manual run)
echo ============================================================
echo.
echo   This will call the model 3 times and use credit.
echo   Expected runtime: about 5-6 minutes.
echo.
echo   Reports go to:  %OUTDIR%
echo   Logs go to:     %LOGDIR%
echo.
echo   Press Ctrl+C to cancel, or
pause

if not exist "%PIPELINE%" (
  echo.
  echo ERROR: pipeline not found: %PIPELINE%
  pause
  exit /b 1
)

call "%PIPELINE%"
set "RC=%ERRORLEVEL%"

echo.
echo ============================================================
if "%RC%"=="0" goto :rep_ok
if "%RC%"=="2" goto :rep_busy

echo   FINISHED WITH PROBLEMS  ^(exit code %RC%^)
echo   Check the newest summary log in:
echo     %LOGDIR%
goto :rep_done

:rep_busy
echo   NOT STARTED - another run is already in progress.
echo   Nothing was changed. Wait for it to finish, then try again.
goto :rep_done

:rep_ok
echo   DONE - all reports generated successfully.

:rep_done
echo ============================================================
echo.
echo Opening the report folder...
start "" "%OUTDIR%"
echo.
pause
exit /b %RC%
