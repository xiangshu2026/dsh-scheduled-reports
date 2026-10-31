# DSH 定时报告 · 无人值守报告生成与归档
# https://github.com/xiangshu2026/dsh-scheduled-reports
# get-api-key.ps1
# Emit the DEEPSEEK_API_KEY ref from ~/.dsh/.credentials.yaml on stdout,
# or nothing at all when the ref is absent. Never writes the key to a log.
#
# Why this exists: "dsh headless" uses the headless profile, which only
# reads provider keys from the process environment. A scheduled task
# starts with a clean environment, so the key must be injected by the
# caller. See run-daily-task.cmd for the full story.

$ErrorActionPreference = 'Stop'

$cred = Join-Path $env:USERPROFILE '.dsh\.credentials.yaml'
if (-not (Test-Path -LiteralPath $cred)) { exit 0 }

$inRefs = $false
foreach ($line in Get-Content -LiteralPath $cred) {
    # Track the top-level "refs:" block; stop at the next top-level key.
    if ($line -match '^refs\s*:') { $inRefs = $true; continue }
    if ($inRefs -and $line -match '^[A-Za-z_]') { break }
    if (-not $inRefs) { continue }

    if ($line -match '^\s+DEEPSEEK_API_KEY\s*:\s*(.+?)\s*$') {
        $value = $matches[1].Trim().Trim('"').Trim("'")
        if ($value) { Write-Output $value }
        break
    }
}
