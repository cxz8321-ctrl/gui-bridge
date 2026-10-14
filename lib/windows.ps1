# gui-bridge · 顶层窗口清单（含位置/大小/进程/标题）
# DPI：进程声明 per-monitor v2，保证这里报的窗口坐标 = 截图的物理像素（否则会差一个缩放倍率）
Add-Type @"
using System;using System.Runtime.InteropServices;
public class DpiW {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr ctx);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@ -ErrorAction SilentlyContinue
try { [DpiW]::SetProcessDpiAwarenessContext([IntPtr]-4) | Out-Null } catch { try { [DpiW]::SetProcessDPIAware() | Out-Null } catch {} }

$out = @()
Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | Sort-Object ProcessName | ForEach-Object {
  $h = $_.MainWindowHandle
  $rect = ''
  try {
    Add-Type @"
using System;using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
public struct RECT { public int Left,Top,Right,Bottom; } }
"@ -ErrorAction SilentlyContinue
    $r = New-Object W+RECT
    if ([W]::GetWindowRect($h, [ref]$r)) { $rect = "($($r.Left),$($r.Top)) $($r.Right-$r.Left)x$($r.Bottom-$r.Top)" }
  } catch {}
  $out += ('{0} | pid {1} | {2} | {3}' -f $_.ProcessName, $_.Id, $rect, $_.MainWindowTitle)
}
$out | ForEach-Object { $_ }
Write-Output ('TOTAL=' + $out.Count)
