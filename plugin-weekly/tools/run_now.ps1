# 立刻跑一次并打开报告
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
python run_weekly.py @args
$report = Join-Path $root "reports\latest.md"
if (Test-Path $report) { Start-Process $report }
