# Phone access to Hassan via Tailscale (private to your own tailnet; never `funnel`).
#   powershell -ExecutionPolicy Bypass -File phone_access.ps1 on      # publish https://<laptop>.<tailnet>.ts.net
#   powershell -ExecutionPolicy Bypass -File phone_access.ps1 off     # stop it (tailscale serve reset)
#   powershell -ExecutionPolicy Bypass -File phone_access.ps1 status
# See docs\jarvis\PHONE_ACCESS.md.
param([ValidateSet("on", "off", "status")][string]$Mode = "on", [int]$Port = 8340)

$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts) {
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base -and (Test-Path "$base\Tailscale\tailscale.exe")) { $ts = "$base\Tailscale\tailscale.exe"; break }
    }
}
if (-not $ts) {
    if ($Mode -ne "on") { Write-Host "Tailscale is not installed." }
    exit 0   # quietly skip: Hassan still works on http://localhost:$Port
}

if ($Mode -eq "off") { & $ts serve reset; Write-Host "Phone access is off."; exit 0 }
if ($Mode -eq "status") { & $ts serve status; & $ts funnel status; exit 0 }

try { $st = & $ts status --json 2>$null | ConvertFrom-Json } catch { $st = $null }
if (-not $st -or $st.BackendState -ne "Running") {
    Write-Host "Tailscale is installed but not connected; phone access skipped. Open Tailscale and sign in."
    exit 0
}

# `tailscale serve` waits if HTTPS is not enabled for the tailnet yet, so never let it hold up Hassan.
$p = Start-Process -FilePath $ts -ArgumentList "serve", "--bg", "$Port" -NoNewWindow -PassThru
$null = $p.Handle   # cache the handle, otherwise ExitCode stays empty after exit
if (-not $p.WaitForExit(20000)) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Tailscale serve did not finish. Enable HTTPS: https://login.tailscale.com/admin/dns (HTTPS Certificates)."
    exit 0
}
$name = "$($st.Self.DNSName)".TrimEnd(".")
if ($p.ExitCode -eq 0 -and $name) { Write-Host "Phone: https://$name/   (only your own Tailscale devices)" }
