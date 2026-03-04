# ============================================
# tapnow-online - Unified Docker Image
# 前端构建 + Python后端服务 (单一镜像)
# ============================================

# ============================================
# Stage 1: 构建前端
# ============================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# 可选：前端构建时注入本地服务地址（优先级高于自动推断）
ARG VITE_LOCAL_SERVER_URL=
ENV VITE_LOCAL_SERVER_URL=${VITE_LOCAL_SERVER_URL}

# 安装依赖
COPY package*.json ./
RUN npm ci --production=false

# 复制源码并构建
COPY . .
RUN npm run build

# ============================================
# Stage 2: Python运行时 + 静态文件服务
# ============================================
FROM python:3.11-slim

LABEL maintainer="tapnow-online"
LABEL description="tapnow-online - Unified Web + API Server"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装Python依赖
COPY localserver/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制Python后端代码
COPY localserver/ ./localserver/

# 创建数据目录
RUN mkdir -p /app/data

# 从前端构建阶段复制构建产物到静态文件目录
COPY --from=frontend-builder /app/dist/ ./static/

# ============================================
# 环境变量配置
# ============================================
# 功能开关
ENV TAPNOW_ENABLE_FILE_SERVER=true
ENV TAPNOW_ENABLE_PROXY=true
ENV TAPNOW_ENABLE_COMFY=false
ENV TAPNOW_ENABLE_LOG=true

# 静态文件目录配置
ENV TAPNOW_STATIC_DIR=/app/static
ENV TAPNOW_SAVE_PATH=/app/data

# 端口 (统一使用 8080)
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping')" || exit 1

# 启动命令 - 使用统一端口8080，并启用静态文件服务
WORKDIR /app/localserver
CMD ["python", "server.py", "-p", "8080", "-d", "/app/data", "--static-dir", "/app/static"]
