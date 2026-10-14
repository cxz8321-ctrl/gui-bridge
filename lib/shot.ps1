# gui-bridge · 抓屏（Windows 侧执行）
# OUT 环境变量 = WSL 目标路径；图像经内存缓冲写出（GDI+ 不支持直接存 UNC）
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System;using System.Runtime.InteropServices;
public class Dpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
"@
[Dpi]::SetProcessDPIAware() | Out-Null   # 拿物理像素，不被 200% 缩放砍半

$out = $env:OUT
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
$g.Dispose()

$ms = New-Object System.IO.MemoryStream
$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

$unc = '\\wsl.localhost\Ubuntu' + ($out -replace '/', '\')
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($unc)) | Out-Null
[System.IO.File]::WriteAllBytes($unc, $ms.ToArray())
$ms.Dispose()

Write-Output ('SAVED ' + $b.Width + 'x' + $b.Height)
