#!/bin/bash
# ─── Deploy Cloud Gateway lên Ubuntu/Debian VPS ──────────────────────────────
# Chạy 1 lần trên Cloud VPS với quyền root:
#   chmod +x deploy_cloud.sh && sudo ./deploy_cloud.sh
#
# Yêu cầu: đã upload thư mục cloud_gateway/ lên VPS
# Upload từ máy Windows:
#   scp -r cloud_gateway/ root@<VPS_IP>:/root/

set -e   # dừng ngay nếu có lỗi

FRP_VERSION="0.62.1"
GATEWAY_DIR="/etc/agv-gateway"

echo "======================================================"
echo " AGV Cloud Gateway — Deploy Script"
echo "======================================================"

# ─── 1. Cài Python và Nginx ──────────────────────────────────────────────────
echo ""
echo "[1/5] Cài dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip nginx certbot python3-certbot-nginx

# ─── 2. Cài frps ─────────────────────────────────────────────────────────────
echo ""
echo "[2/5] Cài frp server..."
FRP_URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz"
wget -q "$FRP_URL" -O /tmp/frp.tar.gz
tar -xzf /tmp/frp.tar.gz -C /tmp/
cp "/tmp/frp_${FRP_VERSION}_linux_amd64/frps" /usr/local/bin/
chmod +x /usr/local/bin/frps
rm -rf /tmp/frp*

mkdir -p /etc/frp
cp config/frps.toml /etc/frp/frps.toml

cp systemd/frps.service /etc/systemd/system/frps.service
systemctl daemon-reload
systemctl enable frps
systemctl restart frps
echo "  ✓ frps đang chạy: $(systemctl is-active frps)"

# ─── 3. Deploy Cloud API Gateway ─────────────────────────────────────────────
echo ""
echo "[3/5] Deploy API Gateway..."
mkdir -p "$GATEWAY_DIR"
cp gateway/gateway.py    "$GATEWAY_DIR/gateway.py"
cp gateway/requirements.txt "$GATEWAY_DIR/requirements.txt"

# Chỉ copy factories.json nếu chưa có (để không ghi đè config đang dùng)
if [ ! -f "$GATEWAY_DIR/factories.json" ]; then
    cp gateway/factories.json "$GATEWAY_DIR/factories.json"
    echo "  → Đã tạo factories.json (template). Nhớ sửa lại cho đúng nhà máy!"
else
    echo "  → factories.json đã tồn tại, giữ nguyên."
fi

python3 -m venv "$GATEWAY_DIR/venv"
"$GATEWAY_DIR/venv/bin/pip" install -q -r "$GATEWAY_DIR/requirements.txt"

cp systemd/agv-gateway.service /etc/systemd/system/agv-gateway.service
systemctl daemon-reload
systemctl enable agv-gateway
systemctl restart agv-gateway
echo "  ✓ agv-gateway đang chạy: $(systemctl is-active agv-gateway)"

# ─── 4. Cấu hình Nginx ───────────────────────────────────────────────────────
echo ""
echo "[4/5] Cấu hình Nginx..."
cp config/nginx.conf /etc/nginx/sites-available/iot.tot360.com.vn

# Chỉ tạo symlink nếu chưa có
if [ ! -f /etc/nginx/sites-enabled/iot.tot360.com.vn ]; then
    ln -s /etc/nginx/sites-available/iot.tot360.com.vn /etc/nginx/sites-enabled/
fi

nginx -t
systemctl reload nginx
echo "  ✓ Nginx đã reload"

# ─── 5. Mở firewall ──────────────────────────────────────────────────────────
echo ""
echo "[5/5] Mở firewall..."
ufw allow 7000/tcp comment "frp tunnel port" 2>/dev/null || true
ufw allow 80/tcp   comment "HTTP"             2>/dev/null || true
ufw allow 443/tcp  comment "HTTPS"            2>/dev/null || true

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo " Deploy hoàn tất!"
echo "======================================================"
echo ""
echo "Bước tiếp theo:"
echo "  1. Sửa /etc/frp/frps.toml — đổi auth.token thành chuỗi ngẫu nhiên"
echo "  2. Sửa /etc/agv-gateway/factories.json — điền đúng nhà máy"
echo "  3. Lấy SSL cert: certbot --nginx -d iot.tot360.com.vn"
echo "  4. Restart services: systemctl restart frps agv-gateway"
echo ""
echo "Kiểm tra:"
echo "  curl https://iot.tot360.com.vn/_gateway/health"
echo ""
echo "Log:"
echo "  journalctl -u agv-gateway -f"
echo "  journalctl -u frps -f"
