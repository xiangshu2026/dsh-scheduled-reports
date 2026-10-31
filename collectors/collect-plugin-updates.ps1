<#
  collect-plugin-updates.ps1

  采集「已安装 DSH 插件的更新情况」，供每日任务 5-plugin-updates.md 使用。

  为什么必须在沙盒外跑：
    - agent 沙盒读不到 profile 的 node_modules 完整结构
    - agent 沙盒没有网络权限去查 npm registry
    所以这里用完整权限查好，落成纯文本，agent 只负责读和写报告。

  输出格式是 KEY=VALUE 与分节，方便 agent 稳定解析。
#>

# DSH 定时报告 · 无人值守报告生成与归档
# https://github.com/xiangshu2026/dsh-scheduled-reports

param(
  [Parameter(Mandatory = $true)][string]$OutFile,
  [string]$ProfileDir = "$env:USERPROFILE\.dsh\profiles\desktop",
  [int]$TimeoutSec = 20
)

$ErrorActionPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$lines = New-Object System.Collections.ArrayList
function Add-Line([string]$text) { [void]$lines.Add($text) }

function Write-Result {
  $dir = Split-Path -Path $OutFile -Parent
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $lines -join [Environment]::NewLine | Out-File -FilePath $OutFile -Encoding utf8
}

Add-Line "# 插件更新采集报告"
Add-Line "GENERATED_AT=$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
Add-Line "PROFILE_DIR=$ProfileDir"
Add-Line ""

# --- 1. 读 profile 的 package.json ---
$pkgPath = Join-Path $ProfileDir 'package.json'
if (-not (Test-Path $pkgPath)) {
  Add-Line "FATAL=profile package.json not found: $pkgPath"
  Write-Result
  exit 1
}

try {
  $pkg = Get-Content $pkgPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
  Add-Line "FATAL=cannot parse package.json: $($_.Exception.Message)"
  Write-Result
  exit 1
}

$deps = @()
if ($pkg.dependencies) {
  foreach ($p in $pkg.dependencies.PSObject.Properties) {
    $obj = New-Object psobject
    $obj | Add-Member -NotePropertyName Name -NotePropertyValue $p.Name
    $obj | Add-Member -NotePropertyName Declared -NotePropertyValue ([string]$p.Value)
    $deps += $obj
  }
}
$bundles = @()
if ($pkg.dsh -and $pkg.dsh.profile -and $pkg.dsh.profile.bundles) {
  $bundles = @($pkg.dsh.profile.bundles)
}

Add-Line "DEP_COUNT=$($deps.Count)"
Add-Line "BUNDLE_COUNT=$($bundles.Count)"
Add-Line ""

# --- 2. 逐个查 npm registry ---
Add-Line "=== PLUGIN_STATUS ==="
Add-Line "# 字段：name | installed | latest | status | published | error"

$outdated = @()
$failed = @()
$uptodate = 0
$checked = 0

foreach ($d in $deps) {
  $name = $d.Name
  $declared = $d.Declared

  # 读实际安装版本
  $installed = ''
  $rel = 'node_modules' + [IO.Path]::DirectorySeparatorChar + ($name -replace '/', [IO.Path]::DirectorySeparatorChar)
  $instPkg = Join-Path $ProfileDir ($rel + [IO.Path]::DirectorySeparatorChar + 'package.json')
  if (Test-Path -LiteralPath $instPkg) {
    try { $installed = [string](Get-Content $instPkg -Raw -Encoding UTF8 | ConvertFrom-Json).version } catch {}
  }
  if (-not $installed) {
    # 可能是 link: 或 file: 本地插件，标注出来
    if ($declared -match '^(link:|file:)') {
      Add-Line "$name|LOCAL|LOCAL|local-link|$declared|-"
      continue
    }
    Add-Line "$name|MISSING|?|installed-missing|$declared|-"
    $failed += $name
    continue
  }

  # 查 registry
  $checked++
  $latest = ''
  $published = ''
  $err = ''
  try {
    $enc = [Uri]::EscapeDataString($name)
    $resp = Invoke-RestMethod -Uri "https://registry.npmjs.org/$enc" -TimeoutSec $TimeoutSec -UseBasicParsing
    $latest = [string]$resp.'dist-tags'.latest
    if ($latest -and $resp.time -and $resp.time.$latest) {
      $published = ([datetime]$resp.time.$latest).ToString('yyyy-MM-dd HH:mm')
    }
  } catch {
    $err = ($_.Exception.Message -replace '[\r\n]+', ' ').Substring(0, [Math]::Min(120, $_.Exception.Message.Length))
  }

  if (-not $latest) {
    Add-Line "$name|$installed|?|registry-error|$declared|$err"
    $failed += $name
    continue
  }

  # 版本比较
  $status = ''
  try {
    $vi = [version]($installed -replace '-.*$', '')
    $vl = [version]($latest -replace '-.*$', '')
    if ($vl -gt $vi) { $status = 'outdated' }
    elseif ($vl -eq $vi) { $status = 'current' }
    else { $status = 'ahead' }
  } catch {
    if ($installed -eq $latest) { $status = 'current' } else { $status = 'unknown' }
  }

  if ($status -eq 'outdated') {
    $obj = New-Object psobject
    $obj | Add-Member -NotePropertyName Name -NotePropertyValue $name
    $obj | Add-Member -NotePropertyName Installed -NotePropertyValue $installed
    $obj | Add-Member -NotePropertyName Latest -NotePropertyValue $latest
    $obj | Add-Member -NotePropertyName Published -NotePropertyValue $published
    $outdated += $obj
  }
  if ($status -eq 'current') { $uptodate++ }

  Add-Line "$name|$installed|$latest|$status|$declared|$published"
}

Add-Line ""
Add-Line "=== SUMMARY ==="
Add-Line "CHECKED=$checked"
Add-Line "OUTDATED_COUNT=$($outdated.Count)"
Add-Line "CURRENT_COUNT=$uptodate"
Add-Line "ERROR_COUNT=$($failed.Count)"
Add-Line ""

# --- 3. 待更新明细（agent 写报告时直接用） ---
Add-Line "=== OUTDATED_DETAIL ==="
if ($outdated.Count -eq 0) {
  Add-Line "(none)"
} else {
  foreach ($o in ($outdated | Sort-Object Name)) {
    Add-Line "$($o.Name)|$($o.Installed)|$($o.Latest)|$($o.Published)"
  }
}
Add-Line ""

# --- 4. 查不到的项目 ---
Add-Line "=== ERROR_DETAIL ==="
if ($failed.Count -eq 0) {
  Add-Line "(none)"
} else {
  foreach ($f in $failed) { Add-Line $f }
}
Add-Line ""

# --- 5. 上一次检查记录（用于判断"是否刚更新过"） ---
# 状态文件固定落在 scheduled 目录（脚本自己所在目录），不跟着 OutFile 走
$stateFile = Join-Path $PSScriptRoot 'plugin-update-state.txt'
Add-Line "=== PREVIOUS_STATE ==="
if (Test-Path $stateFile) {
  Get-Content $stateFile -Encoding UTF8 | ForEach-Object { Add-Line $_ }
} else {
  Add-Line "(first-run)"
}

# 落盘本次状态，供下次对比
try {
  $state = @("LAST_CHECK=$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))")
  foreach ($d in $deps) {
    $rel = 'node_modules' + [IO.Path]::DirectorySeparatorChar + ($d.Name -replace '/', [IO.Path]::DirectorySeparatorChar)
    $instPkg = Join-Path $ProfileDir ($rel + [IO.Path]::DirectorySeparatorChar + 'package.json')
    $v = ''
    if (Test-Path -LiteralPath $instPkg) { try { $v = [string](Get-Content $instPkg -Raw -Encoding UTF8 | ConvertFrom-Json).version } catch {} }
    if ($v) { $state += "$($d.Name)=$v" }
  }
  $state -join [Environment]::NewLine | Out-File -FilePath $stateFile -Encoding utf8
} catch {}

Write-Result
exit 0
