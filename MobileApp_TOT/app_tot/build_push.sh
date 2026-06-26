#!/bin/bash
# ================================================================
# build_push.sh — Build Docker image và push lên Docker Hub
#
# Cách dùng:
#   ./build_push.sh                         # dùng giá trị mặc định
#   ./build_push.sh myuser/agv-mobile       # chỉ định image name
#   API_BASE_URL=https://api.totngv.com ./build_push.sh
# ================================================================
set -e

# ── Cấu hình ─────────────────────────────────────────────────────
DOCKER_USER="${DOCKER_USER:-ducmanh1801}"
IMAGE_NAME="${1:-${DOCKER_USER}/agv-mobile}"
API_BASE_URL="${API_BASE_URL:-https://api.company.com}"
TAG=$(date +%Y%m%d-%H%M)

echo "============================================"
echo "  Build & Push AGV Mobile Web"
echo "  Image : ${IMAGE_NAME}"
echo "  Tags  : latest, ${TAG}"
echo "  API   : ${API_BASE_URL}"
echo "============================================"

# ── Build ─────────────────────────────────────────────────────────
echo ""
echo "[1/3] Building Docker image..."
docker build \
  --build-arg API_BASE_URL="${API_BASE_URL}" \
  --tag "${IMAGE_NAME}:latest" \
  --tag "${IMAGE_NAME}:${TAG}" \
  --progress=plain \
  .

echo ""
echo "[2/3] Image size:"
docker images "${IMAGE_NAME}:latest" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# ── Push ──────────────────────────────────────────────────────────
echo ""
echo "[3/3] Pushing to Docker Hub..."
docker push "${IMAGE_NAME}:latest"
docker push "${IMAGE_NAME}:${TAG}"

echo ""
echo "✅ Done! Image pushed:"
echo "   ${IMAGE_NAME}:latest"
echo "   ${IMAGE_NAME}:${TAG}"
echo ""
echo "▶  Deploy trên cloud server:"
echo "   docker pull ${IMAGE_NAME}:latest"
echo "   docker-compose up -d"
