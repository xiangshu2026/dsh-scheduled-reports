@echo off
REM DSH-Sentinel wrapper - ASCII only (cmd.exe parses batch by byte offset,
REM so any non-ASCII here would corrupt the parsing of later lines).
REM
REM What it does, in order:
REM   1) ledger --sync     register any newly appended audit lines
REM   2) ledger --verify   check the audit log has not been altered
REM   3) sentinel --line   one-line health summary of the report pipeline
REM
REM Exit codes: 1 = audit log tampered with, 2 = sentinel found a real
REM problem. A sentinel warning alone still exits 0 - if warnings made the
REM scheduled task look failed, people would stop reading the output.

setlocal
set "SCHED=%~dp0"

REM Locate node: NODE_EXE env var, then the DSH bundled runtime, then PATH.
set "NODE="
if defined NODE_EXE set "NODE=%NODE_EXE%"
if not defined NODE if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe" set "NODE=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
if not defined NODE if exist "%LOCALAPPDATA%\Programs\DeepSeek Harness\resources\runtime\node\node.exe" set "NODE=%LOCALAPPDATA%\Programs\DeepSeek Harness\resources\runtime\node\node.exe"
if not defined NODE for /f "delims=" %%x in ('where node 2^>nul') do if not defined NODE set "NODE=%%x"

if not defined NODE (
  echo ERROR: node not found. Set NODE_EXE or install Node.js.
  exit /b 2
)

set "SENT=%SCHED%collectors\sentinel.mjs"
set "LEDGER=%SCHED%collectors\audit-ledger.mjs"
set "LOG=%SCHED%logs\sentinel.log"
set "LEDLOG=%SCHED%logs\ledger.log"

if not exist "%SCHED%logs" mkdir "%SCHED%logs"

REM 1) sync first: new lines get registered before verification.
REM    Running verify before sync would report every appended line as tampering.
if exist "%LEDGER%" (
  "%NODE%" "%LEDGER%" --sync >> "%LEDLOG%" 2>&1

  REM 2) then verify integrity
  "%NODE%" "%LEDGER%" --verify --quiet >> "%LEDLOG%" 2>&1
  set LEDGER_CODE=%ERRORLEVEL%
) else (
  echo [sentinel] audit-ledger.mjs not found, skipping ledger check >> "%LEDLOG%"
  set LEDGER_CODE=0
)

REM 3) sentinel health line
if exist "%SENT%" (
  "%NODE%" "%SENT%" --line >> "%LOG%" 2>&1
  set SENT_CODE=%ERRORLEVEL%
) else (
  echo [sentinel] sentinel.mjs not found >> "%LOG%"
  set SENT_CODE=2
)

if %LEDGER_CODE% NEQ 0 exit /b 1
if %SENT_CODE% GEQ 2 exit /b 2
exit /b 0
