-- seed_agv_devices.sql
-- Giữ lại danh sách AGV đã cấu hình (name/loại xe/mạng), KHÔNG mang theo
-- map_id/last_tag/last_seen — vì map sẽ được import mới từ file draw.io trên
-- máy client, gán map lại cho AGV qua giao diện Quản lý AGV sau khi import xong.
-- Chạy SAU schema_core.sql.

INSERT INTO agv_devices
    (name, agv_type, ip, port, factory, subnet, gateway, dns, can_reverse)
VALUES
    ('AGV01', 'trailer', '192.168.0.191', NULL, 'Vonhai',
     '255.255.255.0', '192.168.0.1', '8.8.8.8', FALSE)
ON CONFLICT (name) DO UPDATE SET
    agv_type    = EXCLUDED.agv_type,
    ip          = EXCLUDED.ip,
    factory     = EXCLUDED.factory,
    subnet      = EXCLUDED.subnet,
    gateway     = EXCLUDED.gateway,
    dns         = EXCLUDED.dns,
    can_reverse = EXCLUDED.can_reverse;
