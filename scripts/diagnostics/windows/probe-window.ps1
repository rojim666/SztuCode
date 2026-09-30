$ErrorActionPreference = "Stop"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinProbe {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT p);
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out RECT value, int size);
  [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hwnd, int attr, out int value, int size);
}
"@
$p = Get-Process sztucode-desktop | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$h = $p.MainWindowHandle
$wr = New-Object WinProbe+RECT; [void][WinProbe]::GetWindowRect($h,[ref]$wr)
$cr = New-Object WinProbe+RECT; [void][WinProbe]::GetClientRect($h,[ref]$cr)
$pt = New-Object WinProbe+POINT; $pt.X=0; $pt.Y=0; [void][WinProbe]::ClientToScreen($h,[ref]$pt)
$dr = New-Object WinProbe+RECT; $hr=[WinProbe]::DwmGetWindowAttribute($h,9,[ref]$dr,[Runtime.InteropServices.Marshal]::SizeOf($dr))
$corner=0; $hr2=[WinProbe]::DwmGetWindowAttribute($h,33,[ref]$corner,4)
$border=0; $hr3=[WinProbe]::DwmGetWindowAttribute($h,34,[ref]$border,4)
Write-Output ("PID={0} HWND=0x{1:X}" -f $p.Id,$h.ToInt64())
Write-Output ("GetWindowRect          L={0} T={1} R={2} B={3} size={4}x{5}" -f $wr.Left,$wr.Top,$wr.Right,$wr.Bottom,($wr.Right-$wr.Left),($wr.Bottom-$wr.Top))
Write-Output ("DWM extended bounds    L={0} T={1} R={2} B={3} size={4}x{5} hr={6}" -f $dr.Left,$dr.Top,$dr.Right,$dr.Bottom,($dr.Right-$dr.Left),($dr.Bottom-$dr.Top),$hr)
Write-Output ("Client rect on screen  L={0} T={1} size={2}x{3}" -f $pt.X,$pt.Y,($cr.Right-$cr.Left),($cr.Bottom-$cr.Top))
Write-Output ("Insets: DWM-window L={0} T={1} R={2} B={3}; client-window L={4} T={5}" -f ($dr.Left-$wr.Left),($dr.Top-$wr.Top),($wr.Right-$dr.Right),($wr.Bottom-$dr.Bottom),($pt.X-$wr.Left),($pt.Y-$wr.Top))
Write-Output ("DWMWA_WINDOW_CORNER_PREFERENCE={0} hr={1}; DWMWA_BORDER_COLOR=0x{2:X8} hr={3}" -f $corner,$hr2,$border,$hr3)
