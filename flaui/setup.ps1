# 重新获取 FlaUI 的 net48 DLL 到 .\bin（本仓库已内置一份；此脚本用于升级/修复）
# 用法：powershell -ExecutionPolicy Bypass -File setup.ps1 [-Version 5.0.0]
param([string]$Version = '5.0.0')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$here = $PSScriptRoot
$dst  = Join-Path $here 'bin'
$tmp  = Join-Path $env:TEMP ('flaui_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $dst, $tmp | Out-Null

$items = @(
  @{ pkg='flaui.core';                   ver=$Version;     member='lib/net48/FlaUI.Core.dll' },
  @{ pkg='flaui.uia3';                   ver=$Version;     member='lib/net48/FlaUI.UIA3.dll' },
  @{ pkg='interop.uiautomationclient';   ver='10.19041.0'; member='lib/net45/Interop.UIAutomationClient.dll' }
)
foreach ($it in $items) {
  $url = "https://api.nuget.org/v3-flatcontainer/$($it.pkg)/$($it.ver)/$($it.pkg).$($it.ver).nupkg"
  $nup = Join-Path $tmp "$($it.pkg).nupkg"
  Write-Host "downloading $url"
  Invoke-WebRequest -Uri $url -OutFile $nup -UseBasicParsing
  $zip = [System.IO.Compression.ZipFile]::OpenRead($nup)
  try {
    $entry = $zip.Entries | Where-Object { $_.FullName -eq $it.member } | Select-Object -First 1
    if (-not $entry) { throw "member not found: $($it.member)" }
    $out = Join-Path $dst ([System.IO.Path]::GetFileName($it.member))
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $out, $true)
    Write-Host "  -> $out"
  } finally { $zip.Dispose() }
}
Remove-Item $tmp -Recurse -Force
Write-Host 'done.'
