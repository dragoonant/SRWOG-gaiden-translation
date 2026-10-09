# Drive the game in RPCS3 with the default keyboard pad mapping, then screenshot.
# Usage: powershell -File rpcs3_input.ps1 -Keys "X,wait2,DOWN,X" [-Shot]
#   Buttons: X (Cross) C (Circle) Z (Square) V (Triangle) START SELECT UP DOWN LEFT RIGHT
#   waitN = sleep N seconds. Prints the screenshot path when -Shot is given.
param([string]$Keys = "", [switch]$Shot)
Add-Type -Name K -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);'
$map = @{ X=0x58; C=0x43; Z=0x5A; V=0x56; START=0x0D; SELECT=0x20; UP=0x26; DOWN=0x28; LEFT=0x25; RIGHT=0x27; F12=0x7B }
$ws = New-Object -ComObject WScript.Shell
$null = $ws.AppActivate("FPS:")
Start-Sleep -Milliseconds 500
function Press($vk) {
    [W.K]::keybd_event($vk, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 120
    [W.K]::keybd_event($vk, 0, 2, [UIntPtr]::Zero); Start-Sleep -Milliseconds 350
}
foreach ($k in ($Keys -split ',')) {
    $k = $k.Trim().ToUpper()
    if ($k -eq '') { continue }
    if ($k -like 'WAIT*') { Start-Sleep -Seconds ([double]$k.Substring(4)); continue }
    if (-not $map.ContainsKey($k)) { Write-Error "unknown key $k"; exit 1 }
    Press $map[$k]
}
if ($Shot) {
    $dir = "C:\Users\antho\RPCS3\screenshots\BLJS10133"
    $before = (Get-ChildItem $dir -ErrorAction SilentlyContinue | Measure-Object).Count
    Press $map['F12']
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 250
        if ((Get-ChildItem $dir | Measure-Object).Count -gt $before) { break }
    }
    (Get-ChildItem $dir | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
}
