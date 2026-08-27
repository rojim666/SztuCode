Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap('F:\Learning\codinganget\SztuCode\desktop\tests\visual\__tooltip_full.png')
# tooltip box: x=46..160, y=5..37
$minLum = 999
$maxLum = -999
for ($y=5; $y -lt 37; $y++) {
  for ($x=46; $x -lt 160; $x++) {
    $c = $bmp.GetPixel($x,$y)
    $lum = 0.299*$c.R + 0.587*$c.G + 0.114*$c.B
    if ($lum -lt $minLum) { $minLum = $lum }
    if ($lum -gt $maxLum) { $maxLum = $lum }
  }
}
Write-Host ("luminance range " + [Math]::Round($minLum) + " .. " + [Math]::Round($maxLum))
for ($y=5; $y -lt 37; $y++) {
  $line = ""
  for ($x=46; $x -lt 160; $x++) {
    $c = $bmp.GetPixel($x,$y)
    $lum = 0.299*$c.R + 0.587*$c.G + 0.114*$c.B
    # normalize: bg ~48, text ~255
    if ($lum -gt 190) { $ch = "#" } elseif ($lum -gt 120) { $ch = "+" } elseif ($lum -gt 75) { $ch = "-" } elseif ($lum -gt 55) { $ch = "." } else { $ch = " " }
    $line += $ch
  }
  Write-Host $line
}
