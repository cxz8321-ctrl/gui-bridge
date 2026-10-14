# 开发模式 · OCR（Windows 原生 Windows.Media.Ocr，零安装，中文 zh-Hans-CN）
param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
# 关键：让 stdout 以 UTF-8 输出，否则中文经重定向会变 GBK 乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($WinRtTask, $ResultType) {
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  $netTask.Result
}

$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]

# 解码：默认就是 Bgra8（OCR 最爱的格式）。注意：不要传显式像素格式重载，会炸。
$bitmap = $null
$stream = $null
for ($try = 1; $try -le 4; $try++) {
  try {
    $file    = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
    $stream  = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap  = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    if ($bitmap) { break }
  } catch {
    Start-Sleep -Milliseconds 300
  }
}
if (-not $bitmap) { throw '位图解码失败（重试 4 次）' }

$lang   = New-Object Windows.Globalization.Language 'zh-Hans-CN'
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) { throw 'OcrEngine 创建失败' }

$result = $null
for ($try = 1; $try -le 3; $try++) {
  try {
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    if ($result) { break }
  } catch { Start-Sleep -Milliseconds 400 }
}
if (-not $result) { throw 'OCR 识别失败（重试 3 次）' }

$lines = @()
foreach ($ln in $result.Lines) {
  $words = @()
  foreach ($wd in $ln.Words) {
    $r = $wd.BoundingRect
    $words += [pscustomobject]@{ t = $wd.Text; x = [int]$r.X; y = [int]$r.Y; w = [int]$r.Width; h = [int]$r.Height }
  }
  $xs = @($words | ForEach-Object { $_.x }); $ys = @($words | ForEach-Object { $_.y })
  $xe = @($words | ForEach-Object { $_.x + $_.w }); $ye = @($words | ForEach-Object { $_.y + $_.h })
  $x0 = ($xs | Measure-Object -Minimum).Minimum; $y0 = ($ys | Measure-Object -Minimum).Minimum
  $x1 = ($xe | Measure-Object -Maximum).Maximum; $y1 = ($ye | Measure-Object -Maximum).Maximum
  $lines += [pscustomobject]@{
    text  = $ln.Text
    rect  = @([int]$x0, [int]$y0, [int]($x1 - $x0), [int]($y1 - $y0))
    words = $words
  }
}
if ($stream) { $stream.Dispose() }
@{ width = $bitmap.PixelWidth; height = $bitmap.PixelHeight; lines = $lines } | ConvertTo-Json -Depth 6 -Compress
