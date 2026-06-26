# ═══════════════════════════════════════════════════════════════
# Stage 1 — Build Flutter Web
# ═══════════════════════════════════════════════════════════════
FROM debian:bookworm-slim AS builder

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git wget unzip xz-utils zip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Flutter SDK — ghim version để build reproducible
ARG FLUTTER_VERSION=3.24.5
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="${FLUTTER_HOME}/bin:${FLUTTER_HOME}/bin/cache/dart-sdk/bin:${PATH}"

RUN git clone --depth 1 --branch ${FLUTTER_VERSION} \
    https://github.com/flutter/flutter.git ${FLUTTER_HOME} \
    && flutter config --enable-web \
    && flutter precache --web \
    && flutter doctor -v

# ── Copy source & build ─────────────────────────────────────────
WORKDIR /app

# pubspec riêng để tận dụng Docker layer cache:
# chỉ re-run pub get khi pubspec thay đổi, không phải mỗi lần sửa code
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .

# API URL mặc định — override bằng --build-arg khi docker build
ARG API_BASE_URL=http://192.168.0.86:8000

RUN flutter build web \
    --release \
    --web-renderer html \
    --dart-define=API_BASE_URL=${API_BASE_URL}

# ═══════════════════════════════════════════════════════════════
# Stage 2 — Serve với Nginx (image cuối chỉ ~25 MB)
# ═══════════════════════════════════════════════════════════════
FROM nginx:1.27-alpine AS production

# Copy build output từ stage 1
COPY --from=builder /app/build/web /usr/share/nginx/html

# Nginx config (SPA routing + gzip + cache headers)
COPY nginx.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ > /dev/null || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
