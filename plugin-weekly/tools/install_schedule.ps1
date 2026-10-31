# 注册每周任务：每周指定时间自动生成周报
# 用法（普通权限即可，注册到当前用户）：
#   powershell -ExecutionPolicy Bypass -File tools/install_schedule.ps1
# 自定义：-DayOfWeek Friday -Time 21:30
# 卸载：powershell -ExecutionPolicy Bypass -File tools/install_schedule.ps1 -Remove

param(
    [string]$DayOfWeek = "Monday",
    [string]$Time = "11:00",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$taskName = "DSH-Plugin-Weekly-Report"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$runner = Join-Path $root "run_weekly.py"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已移除任务：$taskName"
    exit 0
}

if (-not (Test-Path $runner)) {
    Write-Host "找不到主程序：$runner" -ForegroundColor Red
    exit 1
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Host "找不到 python，请先确认 python 在 PATH 里" -ForegroundColor Red
    exit 1
}

$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $runner + '"') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN + "\" + $env:USERNAME) -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "已注册每周任务：$taskName" -ForegroundColor Green
Write-Host "  时间：每周 $DayOfWeek $Time"
Write-Host "  程序：$runner"
Write-Host "  报告：$(Join-Path $root 'reports')"
Write-Host ""
Write-Host "查看：Get-ScheduledTask -TaskName $taskName"
Write-Host "立即跑一次：Start-ScheduledTask -TaskName $taskName"
Write-Host "移除：powershell -ExecutionPolicy Bypass -File tools/install_schedule.ps1 -Remove"