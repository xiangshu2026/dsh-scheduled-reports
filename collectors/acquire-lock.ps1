# DSH 定时报告 · 无人值守报告生成与归档
# https://github.com/xiangshu2026/dsh-scheduled-reports
# ============================================================
#  acquire-lock.ps1
#
#  Single-instance guard for the report pipeline.
#
#  The pipeline has two entry points:
#    1. the scheduled task   (run-daily-task.cmd, Mondays 09:00)
#    2. the desktop shortcut (run-reports-now.cmd -> run-daily-task.cmd)
#  Task Scheduler's MultipleInstancesPolicy only serialises entry point 1,
#  so a manual double-click during the scheduled run used to start a second
#  copy. Both copies then wrote the same report files and fought each other
#  (seen on 2026-10-05: three overlapping runs, reports half-written).
#
#  Prints OK   -> lock acquired (exit 0)
#  Prints BUSY -> another live run holds it (exit 1)
#
#  IMPORTANT: the lock stores the whole *ancestor chain* of cmd.exe PIDs,
#  not just the direct parent. cmd runs `for /f ... in (`command`)` through
#  a throwaway child cmd.exe, so the direct parent of this script is a
#  process that dies immediately. The real pipeline cmd.exe is one level
#  higher up. Storing every cmd ancestor means a dead throwaway parent
#  cannot make a live run look stale.
#
#  A lock with no live cmd ancestor is stale and gets taken over, so a
#  killed run can never block future runs.
#
#  Keep this file ASCII-only for safety.
# ============================================================
param(
    [string]$LockFile = ''
)

$ErrorActionPreference = 'Continue'
if (-not $LockFile) { $LockFile = Join-Path $PSScriptRoot 'run.lock' }

# ---------- collect our own cmd.exe ancestors FIRST ----------
#  We need this before the stale-lock check: a lock left by a previous run can
#  legitimately contain one of OUR OWN ancestor PIDs (cmd reuses the parent
#  chain when the pipeline is relaunched from the same shell). Comparing
#  against our own chain avoids the self-deadlock seen on 2026-10-19, where a
#  new run saw its own PID in the lock, concluded "another run is active",
#  and hung forever with no child processes.
$cmdPids = New-Object 'System.Collections.Generic.List[int]'
$cur = $PID
for ($hop = 0; $hop -lt 6; $hop++) {
    $parent = 0
    try {
        $me = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $cur) -ErrorAction Stop
        if ($me -and $me.ParentProcessId) { $parent = [int]$me.ParentProcessId }
    }
    catch { break }
    if ($parent -le 0) { break }

    $pproc = Get-Process -Id $parent -ErrorAction SilentlyContinue
    if ($pproc -and $pproc.ProcessName -eq 'cmd') {
        if (-not $cmdPids.Contains($parent)) { $cmdPids.Add($parent) }
    }
    $cur = $parent
}

# ---------- is the existing lock owned by a live cmd that is NOT us? ----------
if (Test-Path -LiteralPath $LockFile) {
    $raw = ''
    try { $raw = (Get-Content -LiteralPath $LockFile -Raw -ErrorAction Stop).Trim() } catch { }

    $heldByOther = $false
    foreach ($piece in ($raw -split ',')) {
        $id = 0
        if (-not [int]::TryParse($piece.Trim(), [ref]$id)) { continue }
        if ($id -le 0) { continue }
        # ignore our own process and our own cmd ancestors
        if ($id -eq $PID) { continue }
        if ($cmdPids.Contains($id)) { continue }
        $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq 'cmd') { $heldByOther = $true; break }
    }

    if ($heldByOther) {
        Write-Output 'BUSY'
        exit 1
    }
    # nothing else alive owns it: stale lock from a killed run
    Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
}


try {
    $value = ($cmdPids -join ',')
    Set-Content -LiteralPath $LockFile -Value $value -Encoding ASCII -ErrorAction Stop
    Write-Output 'OK'
    exit 0
}
catch {
    Write-Output 'BUSY'
    exit 1
}