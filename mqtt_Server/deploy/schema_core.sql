-- schema_core.sql
-- 2 bảng KHÔNG được app tự tạo lúc khởi động (mọi bảng khác app tự CREATE TABLE
-- IF NOT EXISTS sẵn) — bắt buộc phải chạy file này trước khi khởi động server
-- trên 1 database mới, nếu không app sẽ lỗi vì thiếu bảng.

-- gen_random_uuid() có sẵn từ PostgreSQL 13+; extension này chỉ để an toàn
-- cho bản PostgreSQL cũ hơn (nếu máy client dùng bản < 13).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS agv_devices (
    name         TEXT PRIMARY KEY,
    agv_type     TEXT NOT NULL,
    ip           INET,
    port         INTEGER,
    last_seen    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    map_id       TEXT,
    factory      TEXT,
    last_tag     TEXT,
    subnet       TEXT,
    gateway      TEXT,
    dns          TEXT,
    can_reverse  BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS agv_tasks (
    id             SERIAL PRIMARY KEY,
    task_id        VARCHAR(36) DEFAULT (gen_random_uuid())::text,
    agv_id         VARCHAR(50) NOT NULL,
    destination    VARCHAR(50) NOT NULL,
    map_id         VARCHAR(50),
    status         VARCHAR(20) DEFAULT 'pending',
    order_id       VARCHAR(100),
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now(),
    operator_name  TEXT,
    operator_id    TEXT,
    order_info     JSONB,
    CONSTRAINT agv_tasks_task_id_key UNIQUE (task_id)
);
