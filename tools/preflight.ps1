<#
    TASL preflight check.

    Run this BEFORE plugging in ESP32s. It tells you the laptop's IP, whether
    the firewall will let nodes in, and whether the network profile is set in a
    way that allows inbound connections at all.

        powershell -ExecutionPolicy Bypass -File tools\preflight.ps1

    It only reads state. It changes nothing - it prints the commands you need
    if something is wrong.
#>

$ErrorActionPreference = "Continue"
$port = 8000
$problems = @()

Write-Host ""
Write-Host "==================== TASL PREFLIGHT ====================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------- 1. IP -----
Write-Host "1. Laptop IP address" -ForegroundColor White
$ips = Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }

# The right address is the one on the interface carrying the default route.
# Guessing by name breaks on VirtualBox/Hyper-V adapters, which happily look
# like ordinary Ethernet.
$defaultRoute = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
                Sort-Object RouteMetric | Select-Object -First 1
$lanIndex = $defaultRoute.InterfaceIndex
$lanIp    = $null

foreach ($i in $ips) {
    if ($i.InterfaceIndex -eq $lanIndex) {
        $lanIp = $i.IPAddress
        Write-Host ("   {0,-16} {1}" -f $i.IPAddress, $i.InterfaceAlias) -NoNewline
        Write-Host "  <-- use this in the firmware" -ForegroundColor Green
    } else {
        Write-Host ("   {0,-16} {1}  (not the LAN route - ignore)" -f $i.IPAddress, $i.InterfaceAlias) -ForegroundColor DarkGray
    }
}
if (-not $lanIp) { $problems += "Could not identify which interface carries the default route." }
$lanAlias = (Get-NetAdapter -InterfaceIndex $lanIndex -ErrorAction SilentlyContinue).Name

# ------------------------------------------------------- 2. network profile -
Write-Host ""
Write-Host "2. Network profile" -ForegroundColor White
$profiles = Get-NetConnectionProfile
foreach ($p in $profiles) {
    $colour = if ($p.NetworkCategory -eq 'Public') { 'Red' } else { 'Green' }
    Write-Host ("   {0,-22} {1,-14} {2}" -f $p.Name, $p.InterfaceAlias, $p.NetworkCategory) -ForegroundColor $colour
    if ($p.NetworkCategory -eq 'Public' -and $p.InterfaceAlias -notmatch 'Tailscale') {
        $problems += "Network '$($p.Name)' is Public. Windows blocks inbound connections on Public networks."
    }
}

# ------------------------------------------------------------- 3. firewall --
Write-Host ""
Write-Host "3. Firewall rule for port $port" -ForegroundColor White
$rule = Get-NetFirewallRule -DisplayName "TASL Dashboard*" -ErrorAction SilentlyContinue
if ($rule) {
    Write-Host "   FOUND: $($rule.DisplayName)  [Enabled=$($rule.Enabled)]" -ForegroundColor Green
} else {
    Write-Host "   MISSING - ESP32s will not be able to reach the server." -ForegroundColor Red
    $problems += "No firewall rule allowing inbound TCP $port."
}

# ---------------------------------------------------------- 4. Wi-Fi band ---
Write-Host ""
Write-Host "4. Wi-Fi band" -ForegroundColor White
$wifi = netsh wlan show interfaces 2>$null
if ($wifi) {
    $ssid  = ($wifi | Select-String '^\s*SSID\s*:' | Select-Object -First 1) -replace '.*:\s*',''
    $band  = ($wifi | Select-String '^\s*Band\s*:')                          -replace '.*:\s*',''
    $radio = ($wifi | Select-String '^\s*Radio type\s*:')                    -replace '.*:\s*',''
    Write-Host "   SSID  : $ssid"
    Write-Host "   Band  : $band"
    Write-Host "   Radio : $radio"
    if ($band -match '5' -or $ssid -match '5G') {
        Write-Host "   NOTE: ESP32 is 2.4 GHz ONLY and cannot join a 5 GHz SSID." -ForegroundColor Yellow
        Write-Host "         Point the firmware at this router's 2.4 GHz SSID instead." -ForegroundColor Yellow
    }
} else {
    Write-Host "   (not on Wi-Fi, or wlan service unavailable)"
}

# ------------------------------------------------------------- 5. server ----
Write-Host ""
Write-Host "5. Dashboard server" -ForegroundColor White
try {
    Invoke-RestMethod "http://127.0.0.1:$port/api/state" -TimeoutSec 2 | Out-Null
    Write-Host "   RUNNING on port $port" -ForegroundColor Green
} catch {
    Write-Host "   NOT RUNNING - start it with 'python run_server.py'" -ForegroundColor Yellow
}

# -------------------------------------------------------------- summary -----
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
if ($problems.Count -eq 0) {
    Write-Host " READY. Nodes should be able to reach this laptop." -ForegroundColor Green
} else {
    Write-Host " $($problems.Count) PROBLEM(S) TO FIX:" -ForegroundColor Red
    foreach ($p in $problems) { Write-Host "   - $p" -ForegroundColor Red }
    Write-Host ""
    Write-Host " Run these in an ADMIN PowerShell to fix them:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host ("   Set-NetConnectionProfile -InterfaceAlias `"{0}`" -NetworkCategory Private" -f $lanAlias) -ForegroundColor White
    Write-Host ""
    Write-Host '   New-NetFirewallRule -DisplayName "TASL Dashboard (TCP 8000)" `' -ForegroundColor White
    Write-Host '       -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 `' -ForegroundColor White
    Write-Host '       -Profile Private' -ForegroundColor White
}
Write-Host ""
