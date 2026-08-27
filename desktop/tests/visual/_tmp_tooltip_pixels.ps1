Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap('F:\Learning\codinganget\SztuCode\desktop\tests\visual\__tooltip_actual.png')
Write-Host ("size " + $bmp.Width + "x" + $bmp.Height)
$counts = @{}
for ($y=0; $y -lt $bmp.Height; $y++) {
  for ($x=0; $x -lt $bmp.Width; $x++) {
    $c = $bmp.GetPixel($x,$y)
    $key = $c.R.ToString() + "," + $c.G + "," + $c.B
    if ($counts.ContainsKey($key)) { $counts[$key]++ } else { $counts[$key]=1 }
  }
}
$counts.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 20 | ForEach-Object { Write-Host ($_.Key + " " + $_.Value) }
