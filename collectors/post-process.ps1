# DSH 定时报告 · 无人值守报告生成与归档
# https://github.com/xiangshu2026/dsh-scheduled-reports
# ============================================================
#  post-process.ps1
#
#  Runs after the report tasks, outside the agent sandbox.
#
#    1. converts every .md report in the run folder into .docx
#    2. deletes the .md source, but ONLY once a valid .docx exists
#    3. archives stray reports that still sit in the root folder into
#       a dated subfolder (RootDir\YYYY-MM-DD), so the root stays clean
#    4. prunes run folders older than -KeepDays days
#    5. removes the temporary data snapshots
#
#  Layout:
#    RootDir\
#      2026-10-19\
#        <report-name>-2026-10-19.docx
#        <report-name>-2026-10-19.docx
#        ...
#
#  Two output channels on purpose:
#    stdout  -> plain ASCII, so it can be appended to the UTF-8
#               summary log without any codepage surprises
#    -LogDir -> a UTF-8 detail log (post-YYYY-MM-DD.log) that may
#               contain Chinese file names and stays readable
#
#  Keep this file ASCII-only for safety.
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [string]$RootDir = '',
    [Parameter(Mandatory = $true)][string]$LogDir,
    [int]$KeepDays = 7,
    [string]$PythonExe = '',
    [string]$Converter = ''
)

# Resolve a Python interpreter that has python-docx installed.
# Order: explicit -PythonExe, then the DSH bundled runtime, then PATH.
if (-not $PythonExe) {
    $candidates = @(
        (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\DeepSeek Harness\resources\runtime\python\python.exe')
    )
    foreach ($cand in $candidates) {
        if (Test-Path -LiteralPath $cand) { $PythonExe = $cand; break }
    }
    if (-not $PythonExe) {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $PythonExe = $cmd.Source }
    }
    if (-not $PythonExe) {
        $cmd = Get-Command python3 -ErrorAction SilentlyContinue
        if ($cmd) { $PythonExe = $cmd.Source }
    }
}

$ErrorActionPreference = 'Continue'
if (-not $Converter) { $Converter = Join-Path $PSScriptRoot 'md2docx.py' }
if (-not $RootDir) { $RootDir = Split-Path -Parent $WorkDir }

if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$report = Join-Path $LogDir ('post-' + (Get-Date -Format 'yyyy-MM-dd') + '.log')

function Note([string]$m) {
    Add-Content -LiteralPath $report -Encoding UTF8 -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $m)
}

function Say([string]$m) {
    Write-Output ('[post] ' + $m)
}

function Ascii([string]$s) {
    return ($s -replace '[^\x20-\x7E]', '?')
}

Say 'starting'
Note '================ post-processing ================'
Note ('run folder : ' + $WorkDir)
Note ('root folder: ' + $RootDir)

if (-not (Test-Path -LiteralPath $WorkDir)) {
    Say ('ERROR: workdir not found: ' + (Ascii $WorkDir))
    Note ('ERROR: workdir not found: ' + $WorkDir)
    exit 1
}

# ---------- 1. markdown -> docx ----------
$mds = @(Get-ChildItem -LiteralPath $WorkDir -Filter '*.md' -File -ErrorAction SilentlyContinue)
Say ('markdown files found: ' + $mds.Count)
Note ('markdown files found: ' + $mds.Count)
foreach ($md in $mds) { Note ('  source: ' + $md.Name) }

if ($mds.Count -gt 0) {
    if ((Test-Path -LiteralPath $PythonExe) -and (Test-Path -LiteralPath $Converter)) {
        $pyOut = & $PythonExe $Converter $WorkDir 2>&1
        foreach ($line in $pyOut) { Note ('  converter: ' + $line) }
        Say 'conversion step finished'
    }
    else {
        Say 'ERROR: python or converter missing, conversion skipped'
        Note ('ERROR: python missing=' + (-not (Test-Path -LiteralPath $PythonExe)) +
              ' converter missing=' + (-not (Test-Path -LiteralPath $Converter)))
    }
}

# ---------- 2. drop the markdown source once a valid docx exists ----------
$removed = 0
$kept = 0
foreach ($md in $mds) {
    $docx = Join-Path $WorkDir ([IO.Path]::GetFileNameWithoutExtension($md.Name) + '.docx')
    $good = (Test-Path -LiteralPath $docx) -and ((Get-Item -LiteralPath $docx).Length -gt 1024)
    if ($good) {
        Remove-Item -LiteralPath $md.FullName -Force
        $removed++
        Note ('deleted source: ' + $md.Name)
    }
    else {
        $kept++
        Say ('WARNING: kept markdown without a valid docx: ' + (Ascii $md.Name))
        Note ('KEPT source, conversion missing or too small: ' + $md.Name)
    }
}
Say ('sources deleted: ' + $removed + ', kept: ' + $kept)

# ---------- 3. archive stray reports from the root into dated folders ----------
#  Older runs (before the dated-folder layout) left every report flat in the
#  root. Pull each one into RootDir\<date> based on the date in its file name,
#  falling back to its LastWriteTime. Only top-level files are touched.
$moved = 0
if ((Test-Path -LiteralPath $RootDir) -and ($RootDir -ne $WorkDir)) {
    $stray = @(Get-ChildItem -LiteralPath $RootDir -File -ErrorAction SilentlyContinue |
               Where-Object { $_.Extension -eq '.docx' -or $_.Extension -eq '.md' })
    foreach ($f in $stray) {
        $day = $null
        if ($f.BaseName -match '(\d{4}-\d{2}-\d{2})') { $day = $matches[1] }
        if (-not $day) { $day = $f.LastWriteTime.ToString('yyyy-MM-dd') }

        $target = Join-Path $RootDir $day
        if (-not (Test-Path -LiteralPath $target)) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
        }
        $dest = Join-Path $target $f.Name
        if (Test-Path -LiteralPath $dest) {
            Note ('archive skipped, already present: ' + $day + '\' + $f.Name)
            continue
        }
        Move-Item -LiteralPath $f.FullName -Destination $dest -Force
        $moved++
        Note ('archived: ' + $f.Name + ' -> ' + $day + '\')
    }
    Say ('stray reports archived: ' + $moved)
}

# ---------- 4. prune run folders older than KeepDays ----------
$cutoff = (Get-Date).Date.AddDays(-1 * ($KeepDays - 1))
Say ('keeping run folders from ' + $cutoff.ToString('yyyy-MM-dd') + ' onward')
Note ('pruning run folders older than ' + $cutoff.ToString('yyyy-MM-dd') + ' (keeping ' + $KeepDays + ' days including today)')

$pruned = 0
foreach ($d in @(Get-ChildItem -LiteralPath $RootDir -Directory -ErrorAction SilentlyContinue)) {
    if ($d.Name -notmatch '^\d{4}-\d{2}-\d{2}$') { continue }
    $dt = [datetime]::MinValue
    if (-not [datetime]::TryParseExact($d.Name, 'yyyy-MM-dd', $null, [System.Globalization.DateTimeStyles]::None, [ref]$dt)) { continue }
    if ($dt -lt $cutoff) {
        Remove-Item -LiteralPath $d.FullName -Recurse -Force -ErrorAction SilentlyContinue
        $pruned++
        Note ('pruned old run folder: ' + $d.Name)
    }
}
Say ('old run folders pruned: ' + $pruned)

# ---------- 5. remove the temporary data snapshots ----------
foreach ($name in @('system-info.txt', 'plugin-updates.txt')) {
    $snap = Join-Path $WorkDir $name
    if (Test-Path -LiteralPath $snap) {
        Remove-Item -LiteralPath $snap -Force
        Note ('removed temporary ' + $name)
    }
}

# ---------- 6. final listing ----------
$left = @(Get-ChildItem -LiteralPath $WorkDir -File -ErrorAction SilentlyContinue | Sort-Object Name)
Note ('run folder now holds ' + $left.Count + ' file(s):')
foreach ($f in $left) {
    Note ('  ' + $f.Name + '   ' + [math]::Round($f.Length / 1KB, 1) + ' KB')
}
Say ('run folder holds ' + $left.Count + ' file(s)')
Say 'done'
exit 0
