# ─── Cài frpc làm Windows Service (chạy với quyền Administrator) ─────────────
# Cách dùng:
#   1. Đặt frpc.exe và frpc.toml vào cùng 1 thư mục (ví dụ: C:\frp\)
#   2. Sửa frpc.toml cho đúng nhà máy
#   3. Mở PowerShell với quyền Administrator, chạy script này

param(
    [string]$FrpcDir = "C:\frp"
)

$frpcExe  = Join-Path $FrpcDir "frpc.exe"
$frpcConf = Join-Path $FrpcDir "frpc.toml"
$svcName  = "frpc-agv"
$svcDesc  = "frp Client - AGV Cloud Tunnel"

# Kiểm tra file tồn tại
if (-not (Test-Path $frpcExe)) {
    Write-Error "Không tìm thấy $frpcExe — hãy đặt frpc.exe vào $FrpcDir"
    exit 1
}
if (-not (Test-Path $frpcConf)) {
    Write-Error "Không tìm thấy $frpcConf — hãy đặt frpc.toml vào $FrpcDir"
    exit 1
}

# Xóa service cũ nếu có
$existing = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Dừng và xóa service cũ..."
    Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
    sc.exe delete $svcName | Out-Null
    Start-Sleep -Seconds 2
}

# Tạo service mới
Write-Host "Tạo Windows Service '$svcName'..."
$binPath = "`"$frpcExe`" -c `"$frpcConf`""
sc.exe create $svcName binPath= $binPath start= auto DisplayName= $svcDesc | Out-Null
sc.exe description $svcName $svcDesc | Out-Null

# Cấu hình tự restart khi service lỗi
sc.exe failure $svcName reset= 60 actions= restart/5000/restart/10000/restart/30000 | Out-Null

# Khởi động ngay
Write-Host "Khởi động service..."
Start-Service -Name $svcName

Start-Sleep -Seconds 3
$svc = Get-Service -Name $svcName
Write-Host "Trạng thái: $($svc.Status)"

if ($svc.Status -eq "Running") {
    Write-Host "✓ frpc service đã chạy thành công!" -ForegroundColor Green
    Write-Host "  Tunnel sẽ tự kết nối lại sau mỗi lần khởi động máy."
} else {
    Write-Error "Service không khởi động được. Kiểm tra lại frpc.toml và kết nối mạng."
}
