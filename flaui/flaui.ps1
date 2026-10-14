# Dev-mode . FlaUI(UIA3) industrial-grade UI automation driver
# Called from WSL via: powershell -File flaui.ps1 -Cmd <cmd> ...
# Prints ONE line of JSON to stdout.
#
#   flaui.ps1 -Cmd windows
#   flaui.ps1 -Cmd tree    [-Window '<regex>'] [-Depth 4] [-Limit 400]
#   flaui.ps1 -Cmd find    -Name '<text>' [-Exact] [-Type Button] [-Window '<regex>']
#   flaui.ps1 -Cmd click   -Name '<text>' [-Exact] [-Window '<regex>']
#   flaui.ps1 -Cmd settext -Name '<box>' -Value '<s>' [-Window '<regex>']
#   flaui.ps1 -Cmd text    -Name '<text>' [-Window '<regex>']
#   flaui.ps1 -Cmd focus   -Name '<text>' [-Window '<regex>']
#   flaui.ps1 -Cmd focuswin -Window '<regex>'
#
# DLLs are cached at %LOCALAPPDATA%\gui-bridge-flaui\bin (copied from .\bin on first run)

param(
  [Parameter(Mandatory=$true)][string]$Cmd,
  [string]$Name   = "",
  [string]$Value  = "",
  [string]$Type   = "",
  [string]$Window = "",
  [int]$Depth     = 4,
  [int]$Limit     = 400,
  [switch]$Exact
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Fail($m){ @{ ok=$false; error=$m } | ConvertTo-Json -Depth 4 -Compress; exit 0 }
function J($o){ $o | ConvertTo-Json -Depth 6 -Compress }

# ---- DPI: per-monitor v2 so returned coords == physical pixels ----
try {
  Add-Type @"
using System;using System.Runtime.InteropServices;
public class DpiF {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@ -ErrorAction SilentlyContinue
  [DpiF]::SetProcessDpiAwarenessContext([IntPtr]-4) | Out-Null
} catch {}

# ---- locate + load FlaUI DLLs (cache on local disk to avoid UNC load issues) ----
$src   = Join-Path $PSScriptRoot 'bin'
$cache = Join-Path $env:LOCALAPPDATA 'gui-bridge-flaui\bin'
if (!(Test-Path $cache)) { New-Item -ItemType Directory -Force -Path $cache | Out-Null }
foreach ($f in @('Interop.UIAutomationClient.dll','FlaUI.Core.dll','FlaUI.UIA3.dll')) {
  $s = Join-Path $src $f; $d = Join-Path $cache $f
  if (!(Test-Path $d) -or ((Get-Item $s).LastWriteTime -gt (Get-Item $d).LastWriteTime)) {
    Copy-Item $s $d -Force
  }
}
Add-Type -Path (Join-Path $cache 'Interop.UIAutomationClient.dll')
Add-Type -Path (Join-Path $cache 'FlaUI.Core.dll')
Add-Type -Path (Join-Path $cache 'FlaUI.UIA3.dll')

$script:auto = New-Object FlaUI.UIA3.UIA3Automation

function Rect($el) {
  try { $r = $el.BoundingRectangle
        return @([int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height) } catch { return @(0,0,0,0) }
}
function Desc($el) {
  $r = Rect $el
  @{ name=[string]$el.Name; id=[string]$el.AutomationId; type=$el.ControlType.ToString();
     class=[string]$el.ClassName; rect=$r; enabled=$el.IsEnabled }
}
function RootEl {
  if ($Window) {
    $d = $script:auto.GetDesktop()
    $w = $d.FindAllChildren() | Where-Object { $_.Name -match $Window } | Select-Object -First 1
    if (-not $w) { return $null }
    return $w
  }
  $h = [DpiF]::GetForegroundWindow()
  return $script:auto.FromHandle($h)
}
function MatchEl($root) {
  foreach ($e in $root.FindAllDescendants()) {
    $nm = [string]$e.Name
    $okName = if ($Exact) { $nm -eq $Name } else { $nm -like "*$Name*" }
    if (-not $okName) { continue }
    if ($Type -and ($e.ControlType.ToString() -ne $Type)) { continue }
    return $e
  }
  return $null
}
function NeedRoot() {
  $r = RootEl
  if (-not $r) { Fail ("window not found: " + $Window) }
  return $r
}

try {
  switch ($Cmd) {
    'windows' {
      $res = @()
      foreach ($w in $script:auto.GetDesktop().FindAllChildren()) {
        try { if ($w.ControlType.ToString() -ne 'Window') { continue } } catch { continue }
        $wpid = 0; try { $wpid = [int]$w.Properties.ProcessId.Value } catch {}
        $res += @{ title=[string]$w.Name; class=[string]$w.ClassName; pid=$wpid; rect=(Rect $w) }
      }
      J @{ ok=$true; count=$res.Count; windows=$res }
    }
    'tree' {
      $root = NeedRoot
      $out = New-Object System.Collections.ArrayList
      $stack = New-Object System.Collections.Stack
      $stack.Push(@($root,0))
      while ($stack.Count -gt 0 -and $out.Count -lt $Limit) {
        $it = $stack.Pop(); $el = $it[0]; $dp = [int]$it[1]
        $d = Desc $el; $d.depth = $dp
        [void]$out.Add($d)
        if ($dp -lt $Depth) { foreach ($c in $el.FindAllChildren()) { $stack.Push(@($c,$dp+1)) } }
      }
      J @{ ok=$true; window=[string]$root.Name; count=$out.Count; elements=$out }
    }
    'find' {
      $root = NeedRoot; $e = MatchEl $root
      if (-not $e) { J @{ ok=$true; found=$false } }
      else { $d = Desc $e; $d.ok=$true; $d.found=$true; J $d }
    }
    'click' {
      $root = NeedRoot; $e = MatchEl $root
      if (-not $e) { J @{ ok=$true; found=$false } }
      else {
        $how = ''
        try { $inv = $e.Patterns.Invoke.PatternOrDefault; if ($inv) { $inv.Invoke(); $how = 'invoke' } } catch {}
        if (-not $how) {
          $r = Rect $e
          $pt = New-Object System.Drawing.Point ([int]($r[0]+$r[2]/2)), ([int]($r[1]+$r[3]/2))
          [FlaUI.Core.Input.Mouse]::MoveTo($pt); Start-Sleep -Milliseconds 40
          [FlaUI.Core.Input.Mouse]::Click($pt); $how = 'mouse'
        }
        $d = Desc $e; $d.ok=$true; $d.found=$true; $d.how=$how; J $d
      }
    }
    'settext' {
      $root = NeedRoot; $e = MatchEl $root
      if (-not $e) { J @{ ok=$true; found=$false } }
      else {
        $vp = $e.Patterns.Value.PatternOrDefault
        if ($vp) { $vp.SetValue($Value); J @{ ok=$true; found=$true; how='valuepattern' } }
        else { $e.Focus(); [FlaUI.Core.Input.Keyboard]::Type($Value); J @{ ok=$true; found=$true; how='keyboard' } }
      }
    }
    'text' {
      $root = NeedRoot; $e = MatchEl $root
      if (-not $e) { J @{ ok=$true; found=$false } }
      else {
        $val = ''
        try { $vp = $e.Patterns.Value.PatternOrDefault; if ($vp) { $val = [string]$vp.Value } } catch {}
        J @{ ok=$true; found=$true; name=[string]$e.Name; value=$val }
      }
    }
    'focus' {
      $root = NeedRoot; $e = MatchEl $root
      if (-not $e) { J @{ ok=$true; found=$false } }
      else { $e.Focus(); J @{ ok=$true; found=$true; name=[string]$e.Name } }
    }
    'focuswin' {
      $w = $script:auto.GetDesktop().FindAllChildren() | Where-Object { $_.Name -match $Window } | Select-Object -First 1
      if (-not $w) { Fail ("window not found: " + $Window) }
      $w.Focus(); J @{ ok=$true; window=[string]$w.Name }
    }
    default { Fail ("unknown cmd: " + $Cmd) }
  }
} catch {
  Fail $_.Exception.Message
}
