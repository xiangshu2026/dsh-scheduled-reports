# DSH 定时报告 · 无人值守报告生成与归档
# https://github.com/xiangshu2026/dsh-scheduled-reports
# ============================================================
#  collect-system-info.ps1
#
#  Runs OUTSIDE the DSH sandbox (called by run-daily-task.cmd),
#  collects exact system facts, and writes them to a UTF-8 text
#  file that the daily report task can simply read.
#
#  Purpose: inside its sandbox the agent cannot query WMI/CIM, so
#  it used to guess and sometimes reported a wrong boot time.
#  Collecting the facts here removes that guesswork.
#
#  Keep this file ASCII-only for safety.
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$SampleSeconds = 3,
    # Privacy switch. 1 (default) masks details that reveal what software
    # is installed or how the machine is laid out: process names become
    # app-01/app-02, drive letters become disk-1/disk-2, PIDs are hidden.
    # Set to 0 only if you alone ever read these reports.
    [int]$Redact = 1
)

$ErrorActionPreference = 'Continue'
$lines = New-Object 'System.Collections.Generic.List[string]'
$now = Get-Date

$lines.Add('COLLECTED_AT=' + $now.ToString('yyyy-MM-dd HH:mm:ss'))

# ---- operating system: boot time, uptime, memory, commit charge ----
$cpuCount = 0
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) {
    $boot = $os.LastBootUpTime
    $up = $now - $boot
    $lines.Add('BOOT_TIME=' + $boot.ToString('yyyy-MM-dd HH:mm:ss'))
    $lines.Add(('UPTIME={0} days {1} hours {2} minutes' -f $up.Days, $up.Hours, $up.Minutes))
    $lines.Add('UPTIME_HOURS_TOTAL=' + [math]::Round($up.TotalHours, 1))
    $lines.Add('MEMORY_TOTAL_MB=' + [int]($os.TotalVisibleMemorySize / 1024))
    $lines.Add('MEMORY_FREE_MB=' + [int]($os.FreePhysicalMemory / 1024))
    # commit charge: Win32_OperatingSystem carries the real values on x64
    $commitLimit = [int]($os.TotalVirtualMemorySize / 1024)
    $commitFree = [int]($os.FreeVirtualMemory / 1024)
    if ($commitLimit -gt 0) {
        $lines.Add('COMMIT_LIMIT_MB=' + $commitLimit)
        $lines.Add('COMMIT_USED_MB=' + ($commitLimit - $commitFree))
        $lines.Add('COMMIT_USED_PCT=' + [math]::Round(100 * ($commitLimit - $commitFree) / $commitLimit, 1))
    }
}
else {
    $lines.Add('BOOT_TIME=unavailable')
    $lines.Add('UPTIME=unavailable')
}

$cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
if ($cs) {
    $cpuCount = [int]$cs.NumberOfLogicalProcessors
    $lines.Add('LOGICAL_PROCESSORS=' + $cpuCount)
}
if ($cpuCount -le 0) { $cpuCount = [int]$env:NUMBER_OF_PROCESSORS; if ($cpuCount -le 0) { $cpuCount = 1 } }

# ---- fixed drives only ----
$lines.Add('DISKS:')
$diskIdx = 0
foreach ($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
    if ($null -eq $d.Used -or $null -eq $d.Free) { continue }
    if (-not $d.Root -match '^[A-Za-z]:\$') { continue }
    $total = $d.Used + $d.Free
    if ($total -le 0) { continue }
    $diskIdx++
    $label = $d.Root.TrimEnd('\')
    if ($Redact -eq 1) { $label = 'disk-' + $diskIdx }
    $lines.Add(('  {0}  total_GB={1}  used_GB={2}  free_GB={3}  free_pct={4}' -f `
                $label, `
                [math]::Round($total / 1GB, 1), `
                [math]::Round($d.Used / 1GB, 1), `
                [math]::Round($d.Free / 1GB, 1), `
                [math]::Round(100 * $d.Free / $total, 1)))
}

# ---- real-time CPU sampling ----------------------------------
#  "who is busy right now" is what a daily status report needs;
#  lifetime CPU totals just rank long-running background apps.
$lines.Add('TOP_PROCESSES_BY_CPU_NOW:')
$first = @{}
foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
    try { if ($null -ne $p.CPU) { $first[$p.Id] = $p.CPU } } catch { }
}
Start-Sleep -Seconds $SampleSeconds

$results = New-Object 'System.Collections.Generic.List[object]'
foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
    try {
        if ($null -eq $p.CPU) { continue }
        if (-not $first.ContainsKey($p.Id)) { continue }
        $delta = $p.CPU - $first[$p.Id]
        if ($delta -lt 0) { continue }
        $pct = [math]::Round(100 * $delta / ($SampleSeconds * $cpuCount), 2)
        $item = New-Object psobject
        $item | Add-Member NoteProperty Name $p.ProcessName
        $item | Add-Member NoteProperty Id $p.Id
        $item | Add-Member NoteProperty Pct $pct
        $item | Add-Member NoteProperty TotalSeconds ([math]::Round($p.CPU, 1))
        $item | Add-Member NoteProperty WorkMB ([math]::Round($p.WorkingSet64 / 1MB, 0))
        $results.Add($item)
    }
    catch { }
}

$busy = 0
foreach ($r in $results) { $busy += $r.Pct }
$lines.Add('TOTAL_CPU_PCT_NOW=' + [math]::Round($busy, 1))
$lines.Add('(sample window ' + $SampleSeconds + 's, ' + $cpuCount + ' logical processors)')

$procIdx = 0
foreach ($r in ($results | Sort-Object Pct -Descending | Select-Object -First 8)) {
    if ($r.Pct -le 0) { continue }
    $procIdx++
    $pname = $r.Name
    $ppid = $r.Id
    if ($Redact -eq 1) {
        $pname = 'app-' + ('{0:D2}' -f $procIdx)
        $ppid = 'hidden'
    }
    $lines.Add(('  {0}  pid={1}  cpu_now_pct={2}  cpu_seconds_total={3}  ws_MB={4}' -f `
                $pname, $ppid, $r.Pct, $r.TotalSeconds, $r.WorkMB))
}

# ---- lifetime CPU totals, for reference only ----
$lines.Add('TOP_PROCESSES_BY_LIFETIME_CPU (reference only, favours long-running apps):')
$life = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.CPU -gt 0 } |
        Sort-Object CPU -Descending | Select-Object -First 5
$lifeIdx = 0
foreach ($p in $life) {
    $lifeIdx++
    $lname = $p.ProcessName
    $lpid = $p.Id
    if ($Redact -eq 1) {
        $lname = 'app-L' + ('{0:D2}' -f $lifeIdx)
        $lpid = 'hidden'
    }
    $lines.Add(('  {0}  pid={1}  cpu_seconds_total={2}' -f $lname, $lpid, [math]::Round($p.CPU, 1)))
}

# ---- write UTF-8 without BOM ----
try {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($OutFile, $lines, $utf8)
    Write-Output ('OK: system info written to ' + $OutFile)
}
catch {
    Write-Output ('ERROR: could not write ' + $OutFile + ' : ' + $_.Exception.Message)
    exit 1
}
