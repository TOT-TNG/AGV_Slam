# --- Go bo Windows Service frpc-agv (chay voi quyen Administrator) ----------
# Dung khi can: go cai de cai lai tu dau, chuyen may, hoac ngung dung tunnel
# cloud vinh vien tai nha may nay.
#
# Cach dung:
#   .\uninstall_service.ps1                 # chi go service, GIU LAI C:\frp
#   .\uninstall_service.ps1 -RemoveFiles     # go service VA xoa luon C:\frp

param(
    [string]$FrpcDir = "C:\frp",
    [switch]$RemoveFiles
)

$svcName = "frpc-agv"
$nssmExe = Join-Path $FrpcDir "nssm.exe"

$existing = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Khong co service '$svcName' nao dang ton tai - khong can go."
} else {
    Write-Host "Dung service '$svcName'..."
    Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    if (Test-Path $nssmExe) {
        & $nssmExe remove $svcName confirm | Out-Null
    }
    # Fallback neu NSSM khong xoa duoc (vd service cu tao boi sc.exe truoc day)
    sc.exe delete $svcName 2>$null | Out-Null

    Start-Sleep -Seconds 1
    $stillThere = Get-Service -Name $svcName -ErrorAction SilentlyContinue
    if ($stillThere) {
        Write-Error "Khong xoa duoc service '$svcName' - thu chay lai voi quyen Administrator, hoac xoa tay bang 'sc.exe delete $svcName'."
        exit 1
    }
    Write-Host "OK: da go service '$svcName'." -ForegroundColor Green
}

if ($RemoveFiles) {
    if (Test-Path $FrpcDir) {
        Remove-Item $FrpcDir -Recurse -Force
        Write-Host "OK: da xoa thu muc $FrpcDir (bao gom frpc.exe, frpc.toml, nssm.exe, log)." -ForegroundColor Green
    }
    Write-Host "Luu y: Windows Defender exclusion cho $FrpcDir van con - xoa tay tai"
    Write-Host "Windows Security > Virus & threat protection > Exclusions neu muon don sach hoan toan."
} else {
    Write-Host "Giu nguyen thu muc $FrpcDir (frpc.exe, frpc.toml...). Dung -RemoveFiles neu muon xoa het."
}
