Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap('F:\Learning\codinganget\SztuCode\desktop\tests\visual\_tmp_tooltip_live.png')
Write-Host ("size " + $bmp.Width + "x" + $bmp.Height)
for ($y=0; $y -lt $bmp.Height; $y++) {
  $line = ""
  for ($x=0; $x -lt $bmp.Width; $x++) {
    $c = $bmp.GetPixel($x,$y)
    $lum = 0.299*$c.R + 0.587*$c.G + 0.114*$c.B
    if ($lum -gt 190) { $ch = "#" } elseif ($lum -gt 120) { $ch = "+" } elseif ($lum -gt 75) { $ch = "-" } elseif ($lum -gt 55) { $ch = "." } else { $ch = " " }
    $line += $ch
  }
  Write-Host $line
}
