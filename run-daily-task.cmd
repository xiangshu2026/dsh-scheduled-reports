REM DSH Scheduled Reports - unattended report generation and archiving
REM https://github.com/xiangshu2026/dsh-scheduled-reports
@echo off
setlocal

rem ============================================================
rem  DSH daily scheduled task runner  (multi-report version)
rem
rem  Runs every task file listed in TASKLIST, one after another.
rem  Each task gets its own log file; one failing task does not
rem  stop the others.
rem
rem  You normally only change the three settings below.
rem
rem  After the reports are generated this script also converts them
rem  to .docx, deletes the .md sources and prunes old reports.
rem
rem  IMPORTANT: this file must stay pure ASCII. cmd.exe parses
rem  batch files by byte offset, so non-ASCII text here can
rem  corrupt the parsing of later lines. That is also why
rem  WORKDIR uses an ASCII folder name.
rem ============================================================

rem ---------- setting 1: the folder the tasks may touch ----------
rem  Reports are written here. Tasks run from here too.
set "WORKDIR=%USERPROFILE%\Desktop\DSH-Reports"
rem ---------------------------------------------------------------

rem ---------- setting 2: how much freedom the agent gets ----------
rem  workspace-write    = may only read/write inside WORKDIR. Safe.
rem  danger-full-access = may touch anything on this PC. Risky when
rem                       nobody is watching. Change only if a task
rem                       really needs files outside WORKDIR.
set "DSH_PERMISSION_MODE=workspace-write"
rem ---------------------------------------------------------------

rem ---------- setting 3: how many days of reports to keep ----------
rem  Reports older than this are deleted at the end of every run.
rem  The .md sources are always removed once the matching .docx has
rem  been produced, so in the end only Word files remain.
rem
rem  NOTE: the reports now run WEEKLY, so this must be large enough to
rem  keep several weeks. At 7 days each new run would delete the
rem  previous week's reports and only one issue would ever survive.
rem  180 days = about 26 weekly issues.
set "KEEPDAYS=180"
rem ---------------------------------------------------------------

set "SCHED=%~dp0"
set "TASKDIR=%SCHED%tasks"
set "LOGDIR=%SCHED%logs"
rem  Auto-detect the dsh CLI: DSH_CLI env var, then the default desktop
rem  install location, then whatever "dsh" resolves to on PATH.
set "DSH="
if defined DSH_CLI set "DSH=%DSH_CLI%"
if not defined DSH if exist "%LOCALAPPDATA%\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd" set "DSH=%LOCALAPPDATA%\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"
if not defined DSH for /f "delims=" %%x in ('where dsh 2^>nul') do if not defined DSH set "DSH=%%x"
set "TASKLIST=1-computer.md 2-ai-models.md 5-plugin-updates.md"

rem ---------------------------------------------------------------
rem  ---- API key for headless runs ----
rem  The headless profile (@deepseek-ai/dsh-headless) does NOT read
rem  keys from ~/.dsh/.credentials.yaml refs the way the desktop app
rem  does; it only looks at the launching environment. A scheduled
rem  task starts with a clean environment, so every task used to die
rem  with MISSING_CREDENTIAL for provider route "deepseek-official"
rem  (seen 2026-10-19; the last good run was 2026-10-13).
rem
rem  Fix: pull DEEPSEEK_API_KEY out of the credentials refs here and
rem  export it for the child dsh process. The key is never echoed.
rem  If the ref is missing the script warns and keeps going, so the
rem  failure stays visible in the log instead of being masked.
rem ---------------------------------------------------------------
set "DEEPSEEK_API_KEY="
if exist "%USERPROFILE%\.dsh\.credentials.yaml" (
  for /f "usebackq tokens=*" %%k in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%SCHED%collectors\get-api-key.ps1"`) do set "DEEPSEEK_API_KEY=%%k"
)
if defined DEEPSEEK_API_KEY (
  set "KEYSTATE=ok"
) else (
  set "KEYSTATE=MISSING"
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

call :stamp
set "DAY=%NOWDATE%"
set "SUMMARY=%LOGDIR%\summary-%DAY%.log"

rem ---- single-instance guard ----
rem  The scheduled task and the desktop shortcut share this script, and
rem  Task Scheduler's IgnoreNew only serialises the scheduled one. Without
rem  this guard a double-click during an automatic run starts a second copy
rem  and both fight over the same report files (happened 2026-10-05).
set "LOCKFILE=%SCHED%run.lock"
set "LOCKSTATE="
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%SCHED%collectors\acquire-lock.ps1" -LockFile "%LOCKFILE%"`) do set "LOCKSTATE=%%i"
if not "%LOCKSTATE%"=="OK" (
  >>"%SUMMARY%" echo [%NOW%] SKIPPED: another run is already in progress
  echo.
  echo Another run is already in progress - nothing was started.
  echo Wait for it to finish, then try again.
  exit /b 2
)

>>"%SUMMARY%" echo [%NOW%] ================ DAILY RUN ================

if not exist "%WORKDIR%" (
  >>"%SUMMARY%" echo [%NOW%] FATAL: WORKDIR not found: %WORKDIR%
  exit /b 1
)

if not exist "%DSH%" (
  >>"%SUMMARY%" echo [%NOW%] FATAL: dsh launcher not found: %DSH%
  exit /b 1
)

rem ---- per-run output folder: WORKDIR\YYYY-MM-DD ----
rem  Every run gets its own dated subfolder so the report directory does not
rem  grow into a flat pile of files. Reports, the system-info snapshot and the
rem  token dumps all live inside it; post-process.ps1 archives them there.
set "RUNOUT=%WORKDIR%\%DAY%"
if not exist "%RUNOUT%" mkdir "%RUNOUT%"
if errorlevel 1 (
  >>"%SUMMARY%" echo [%NOW%] FATAL: cannot create run folder: %RUNOUT%
  exit /b 1
)

cd /d "%RUNOUT%"
if errorlevel 1 (
  >>"%SUMMARY%" echo [%NOW%] FATAL: cannot enter run folder: %RUNOUT%
  exit /b 1
)

>>"%SUMMARY%" echo [%NOW%] workdir=%WORKDIR%
>>"%SUMMARY%" echo [%NOW%] runout=%RUNOUT%
>>"%SUMMARY%" echo [%NOW%] permission=%DSH_PERMISSION_MODE
>>"%SUMMARY%" echo [%NOW%] api-key=%KEYSTATE%
if not "%KEYSTATE%"=="ok" (
  >>"%SUMMARY%" echo [%NOW%] WARNING: DEEPSEEK_API_KEY not found in .credentials.yaml refs.
  >>"%SUMMARY%" echo [%NOW%] WARNING: every headless task will fail with MISSING_CREDENTIAL.
  >>"%SUMMARY%" echo [%NOW%] WARNING: store the key with the desktop Models page, then re-run.
)

rem ---- collect exact system facts here, outside the agent sandbox ----
rem  The agent cannot query WMI/CIM inside its sandbox, so it used to
rem  guess and sometimes reported a wrong boot time. This runs with
rem  full rights and drops the facts where the report task can read them.
if exist "%SCHED%collectors\collect-system-info.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCHED%collectors\collect-system-info.ps1" -OutFile "%RUNOUT%\system-info.txt" >>"%SUMMARY%" 2>&1
) else (
  >>"%SUMMARY%" echo [%NOW%] WARNING: collect-system-info.ps1 not found, report data may be inaccurate
)

rem ---- collect installed plugin versions vs npm registry ----
rem  The agent sandbox cannot read the full profile node_modules layout nor
rem  reach npm registry, so this runs with full rights and drops plain text
rem  next to the other inputs. Local link:/file:/github: plugins legitimately
rem  404 on npm; the collector marks them registry-error rather than failing.
if exist "%SCHED%collectors\collect-plugin-updates.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%SCHED%collectors\collect-plugin-updates.ps1" -OutFile "%RUNOUT%\plugin-updates.txt" >>"%SUMMARY%" 2>&1
  if errorlevel 1 >>"%SUMMARY%" echo [%NOW%] WARNING: plugin update collector failed
) else (
  >>"%SUMMARY%" echo [%NOW%] WARNING: collect-plugin-updates.ps1 not found, plugin report will be skipped
)

set "FAILED=0"
for %%T in (%TASKLIST%) do (
  call :runtask "%%T"
  if errorlevel 1 set "FAILED=1"
)

rem ---- post-process: md -> docx, drop sources, prune old reports ----
call :stamp
>>"%SUMMARY%" echo [%NOW%] --- post-processing [md to docx, keep %KEEPDAYS% days]
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCHED%collectors\post-process.ps1" -WorkDir "%RUNOUT%" -RootDir "%WORKDIR%" -LogDir "%LOGDIR%" -KeepDays %KEEPDAYS% >>"%SUMMARY%" 2>&1
if errorlevel 1 (
  >>"%SUMMARY%" echo [%NOW%] --- post-processing reported a problem
  set "FAILED=1"
)

call :release

call :stamp
if "%FAILED%"=="1" (
  >>"%SUMMARY%" echo [%NOW%] ============ RUN END: SOME TASKS FAILED ============
  exit /b 1
)
>>"%SUMMARY%" echo [%NOW%] ============ RUN END: ALL OK ============
exit /b 0


rem ------------------------------------------------------------
rem  :release  --  drop the single-instance lock
rem  A killed run leaves the lock behind, but acquire-lock.ps1 treats a
rem  lock whose owning process is gone as stale and takes it over, so a
rem  leftover lock can never block future runs.
rem ------------------------------------------------------------
:release
if defined LOCKFILE del "%LOCKFILE%" 2>nul
goto :eof


rem ------------------------------------------------------------
rem  :runtask <filename>   run one task file through dsh headless
rem ------------------------------------------------------------
:runtask
set "TNAME=%~1"
set "TBASE=%TNAME:.md=%"
set "TFILE=%TASKDIR%\%TNAME%"
set "TLOG=%LOGDIR%\%DAY%-%TBASE%.log"

call :stamp
>>"%TLOG%" echo [%NOW%] ===== START %TNAME% =====
>>"%TLOG%" echo [%NOW%] workdir=%RUNOUT%
>>"%SUMMARY%" echo [%NOW%] --- %TNAME% started

if not exist "%TFILE%" (
  >>"%TLOG%" echo [%NOW%] ERROR: task file not found: %TFILE%
  >>"%SUMMARY%" echo [%NOW%] --- %TNAME% FAILED [task file missing]
  exit /b 1
)

cd /d "%RUNOUT%"

call "%DSH%" headless - < "%TFILE%" >>"%TLOG%" 2>&1
set "CODE=%ERRORLEVEL%"

call :stamp
>>"%TLOG%" echo [%NOW%] ===== END %TNAME% exit=%CODE% =====
if "%CODE%"=="0" (
  >>"%SUMMARY%" echo [%NOW%] --- %TNAME% OK
  exit /b 0
)
>>"%SUMMARY%" echo [%NOW%] --- %TNAME% FAILED exit=%CODE%
exit /b 1


rem ------------------------------------------------------------
rem  :stamp  --  sets NOWDATE (yyyy-MM-dd) and NOW (yyyy-MM-dd HH:mm:ss)
rem              via PowerShell, so the format never depends on the
rem              console locale or codepage.
rem ------------------------------------------------------------
:stamp
set "NOWDATE=unknown"
set "NOW=unknown"
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"`) do set "NOWDATE=%%i"
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"`) do set "NOW=%%i"
goto :eof
