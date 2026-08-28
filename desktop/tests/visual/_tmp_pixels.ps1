Add-Type -AssemblyName System.Drawing
$bmp = [System.Drawing.Bitmap]::FromFile((Resolve-Path 'tests\visual\__tooltip_actual.png'))
# 文字带 y=10..21, x=12..101 — 输出 ASCII 灰度图：白=# 灰=. 黑=空格
for ($y = 10; $y -le 21; $y++) {
  $line = ""
  for ($x = 12; $x -le 101; $x++) {
    $c = $bmp.GetPixel($x, $y)
    $lum = [int](0.299*$c.R + 0.587*$c.G + 0.114*$c.B)
    if ($lum -gt 200) { $line += "#" }
    elseif ($lum -gt 120) { $line += "+" }
    elseif ($lum -gt 80) { $line += "." }
    else { $line += " " }
  }
  Write-Host $line
}
