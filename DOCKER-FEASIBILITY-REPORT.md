# kais-review-platform Docker 部署可行性报告

> **低配机 IP**: 192.168.71.140 | **高配机 Worker**: 192.168.71.38  
> **日期**: 2026-05-05

---

## 1. Docker 资源优化

### 1.1 内存 & CPU 限制

低配机 8-16GB RAM，需严格限制各容器资源，避免 OOM Kill。

```yaml
deploy:
  resources:
    limits:
      cpus: '0.50'
      memory: 512M
    reservations:
      cpus: '0.25'
      memory: 128M
```

### 1.2 镜像瘦身策略

| 策略 | 说明 |
|------|------|
| Alpine/Debian-slim 基础镜像 | Node.js 用 `node:22-alpine`，Nginx 用 `nginx:alpine` |
| 多阶段构建 | 构建阶段用完整镜像，运行阶段仅复制产物 |
| .dockerignore | 排除 node_modules、.git、docs 等 |
| 合并 RUN 层 | 减少镜像层数 |

```dockerfile
# 多阶段构建示例
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

### 1.3 服务拆分建议

**推荐：4 容器方案**（轻量、职责清晰、适合 8GB RAM）

| 服务 | 镜像 | 内存限制 | 预估实际占用 |
|------|------|---------|-------------|
| `api` | node:22-alpine | 512M | 150-256M |
| `nginx` | nginx:alpine | 64M | 16-32M |
| `redis` | redis:alpine | 128M | 32-64M |
| `review-ui` | nginx:alpine (静态) | 32M | 8-16M |

> **总预估**: ~250-400MB，远低于 8GB 限制，留足余量给系统和其他服务。

**不推荐单体方案**：虽然更省内存（~200MB），但失去独立扩缩、独立重启、关注点分离的优势。

**不推荐更多容器拆分**（如单独 worker、sidecar）：在 8GB 机器上，每个容器有基础开销（~10-20MB），过度拆分得不偿失。

---

## 2. 数据持久化

### 2.1 SQLite 在 Docker 中的最佳实践

```yaml
volumes:
  - ./data/review.db:/app/data/review.db  # bind mount，简单直接
  - sqlite-wal:/app/data/                  # WAL 模式的 WAL/SHM 文件
```

**关键注意事项**：
- **必须启用 WAL 模式**：`PRAGMA journal_mode=WAL;`，避免写锁阻塞读操作
- **不要使用网络挂载**（NFS/CIFS）：SQLite 文件锁在网络文件系统上不可靠
- **单进程写入**：SQLite 只支持单写入者，多容器不能同时写同一个 db 文件
- **设置 `PRAGMA busy_timeout=5000;`**：避免写冲突立即报错

### 2.2 数据卷挂载策略

```yaml
# docker-compose.yml
volumes:
  sqlite_data:
    driver: local

services:
  api:
    volumes:
      - ./data:/app/data          # bind mount，方便备份和调试
      - ./uploads:/app/uploads    # 审核素材（图片/视频预览）
```

**推荐 bind mount 而非 named volume**：审核平台的 db 文件不大（<100MB），bind mount 方便直接备份、查看、用 SQLite 工具操作。

### 2.3 备份方案

**推荐：定时 SQLite 备份 + Git 同步**

```bash
#!/bin/bash
# backup.sh - 每小时运行一次
BACKUP_DIR="/home/kai/backup/review-platform"
DATE=$(date +%Y%m%d_%H%M)
DB_PATH="/home/kai/kais-review-platform/data/review.db"

# SQLite 在线备份 API（不锁库）
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/review_${DATE}.db'"

# 保留最近 24 个备份
ls -t "$BACKUP_DIR"/review_*.db | tail -n +25 | xargs -r rm

# 可选：推送到 Git
cd "$BACKUP_DIR" && git add -A && git commit -m "backup $DATE" && git push
```

```yaml
# docker-compose.yml 中添加 backup 服务
  backup:
    image: alpine
    volumes:
      - ./data:/data:ro
      - ./backup:/backup
    entrypoint: /bin/sh
    command: >
      -c "while true; do
        apk add --no-cache sqlite &&
        sqlite3 /data/review.db \".backup '/backup/review_$$(date +%Y%m%d_%H%M).db'\" &&
        ls -t /backup/review_*.db | tail -n +25 | xargs rm -f &&
        sleep 3600;
      done"
    restart: unless-stopped
```

---

## 3. 网络与通信

### 3.1 架构总览

```
┌─────────────────────────────────────────────────┐
│  低配机 192.168.71.140                          │
│  ┌──────────┐   ┌──────────┐   ┌─────────────┐ │
│  │ Nginx    │──▶│ API      │──▶│ SQLite/Redis│ │
│  │ :80/:443 │   │ :3000    │   │             │ │
│  └──────────┘   └────┬─────┘   └─────────────┘ │
│       │              │                          │
│       ▼              ▼                          │
│  ┌──────────┐   HTTP Callback                  │
│  │ Review   │                                  │
│  │ UI       │                                  │
│  └──────────┘                                  │
└──────────────────┬──────────────────────────────┘
                   │ LAN (HTTP API)
                   ▼
┌──────────────────────────────────────────────────┐
│  高配机 192.168.71.38                            │
│  kais-movie-agent / kais-gold-team               │
└──────────────────────────────────────────────────┘
```

### 3.2 API 集成方式

**与 kais-movie-agent**：
- 审核平台提供 REST API：`POST /api/v1/reviews` 提交审核任务
- movie-agent 调用审核 API 提交待审核内容（场景图、分镜等）
- 审核完成后通过 Webhook 回调 movie-agent：`POST http://192.168.71.38:{port}/callback/review`

**与 kais-gold-team**：
- 同样通过 REST API + Webhook 回调
- Worker 在高配机上完成渲染后，通过回调通知审核平台结果已更新

### 3.3 SSE/WebSocket Nginx 反代配置

```nginx
server {
    listen 80;
    server_name 192.168.71.140;

    # 前端静态文件
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # API 反代
    location /api/ {
        proxy_pass http://api:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE 支持
    location /api/v1/stream {
        proxy_pass http://api:3000;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_set_header Cache-Control 'no-cache';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;  # 24h keepalive
        chunked_transfer_encoding off;
    }

    # WebSocket 支持（如果需要）
    location /ws {
        proxy_pass http://api:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }
}
```

### 3.4 Webhook 出站配置

审核平台需要主动向高配机发 HTTP 回调：

```yaml
# docker-compose.yml
services:
  api:
    environment:
      # Webhook 目标地址
      - MOVIE_AGENT_CALLBACK_URL=http://192.168.71.38:8100/callback/review
      - GOLD_TEAM_CALLBACK_URL=http://192.168.71.38:8200/callback/review
      # 本平台外网地址（用于生成审核链接）
      - PLATFORM_BASE_URL=http://192.168.71.140
    # 确保能访问局域网
    extra_hosts:
      - "host.docker.internal:host-gateway"
    network_mode: bridge  # 默认即可，bridge 网络可访问宿主局域网
```

---

## 4. 监控与运维

### 4.1 轻量级监控方案

**推荐：Docker 原生 + 简单脚本，不引入 Prometheus/Grafana（太重）**

```bash
# watch.sh - 简易监控脚本
#!/bin/bash
watch -n 10 'docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"'
```

**可选轻量方案**：
- **ctop**：`docker run -rm -ti --name ctop -v /var/run/docker.sock:/var/run/docker.sock quay.io/vektorlab/ctop:latest`
- **Dozzle**：Web 日志查看器，极轻量（~10MB RAM）
  ```yaml
  dozzle:
    image: amir20/dozzle:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    ports:
      - "127.0.0.1:9999:8080"  # 仅本地访问
    restart: unless-stopped
  ```

### 4.2 日志收集

```yaml
services:
  api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"  # 最多保留 3 个文件，共 30MB
```

### 4.3 健康检查与自动重启

```yaml
services:
  api:
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped

  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 3s
      retries: 3
    restart: unless-stopped
```

---

## 5. 安全性

### 5.1 JWT 认证最佳实践

```yaml
services:
  api:
    environment:
      - JWT_SECRET=${JWT_SECRET}        # 从 .env 文件读取，不硬编码
      - JWT_EXPIRES_IN=24h
      - JWT_REFRESH_EXPIRES_IN=7d
```

**建议**：
- JWT Secret 至少 32 字节随机字符串，存储在 `.env` 文件中
- Access Token 短期（1-2h），Refresh Token 长期（7d）
- Token 存储在 httpOnly cookie 中，防止 XSS
- 敏感操作需要重新认证

### 5.2 审核链接（一次性令牌）设计

```python
# 审核链接生成逻辑
import secrets
import hashlib

def generate_review_token(review_id: str) -> str:
    """生成一次性审核令牌"""
    raw = f"{review_id}:{secrets.token_hex(16)}"
    token = hashlib.sha256(raw.encode()).hexdigest()[:32]
    return token

# 验证逻辑：
# 1. 查询 token 是否存在且未使用
# 2. 验证通过后立即标记为已使用（原子操作）
# 3. 可选：设置过期时间（如 72h）
```

**审核链接格式**：`http://192.168.71.140/review/{review_id}?token={one_time_token}`

**安全措施**：
- 令牌 32 字符，不可猜测
- 一次性使用，验证后立即失效
- 可设置过期时间
- 审核操作需要提交审核意见后才标记为已完成（防止误触）

### 5.3 Docker 安全加固

```yaml
# docker-compose.yml
services:
  api:
    read_only: true           # 只读文件系统（如需写临时文件，用 tmpfs）
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE      # 仅保留绑定端口能力
    user: "1000:1000"         # 非 root 运行

  nginx:
    read_only: true
    tmpfs:
      - /tmp
      - /var/cache/nginx
      - /var/run
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - NET_BIND_SERVICE

  redis:
    # Redis 不支持 read_only，但可以限制能力
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    # 禁用危险命令
    command: redis-server --appendonly yes --maxmemory 64mb --maxmemory-policy allkeys-lru
```

---

## 6. 推荐 Docker Compose 结构

```yaml
# docker-compose.yml
version: '3.9'

services:
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: review-api
    environment:
      - NODE_ENV=production
      - DATABASE_PATH=/app/data/review.db
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET=${JWT_SECRET}
      - PLATFORM_BASE_URL=http://192.168.71.140
      - MOVIE_AGENT_CALLBACK_URL=http://192.168.71.38:8100/callback/review
      - GOLD_TEAM_CALLBACK_URL=http://192.168.71.38:8200/callback/review
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    depends_on:
      redis:
        condition: service_healthy
    expose:
      - "3000"
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop: [ALL]
    cap_add: [NET_BIND_SERVICE]

  nginx:
    image: nginx:alpine
    container_name: review-nginx
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./frontend/dist:/usr/share/nginx/html:ro
    depends_on:
      api:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 64M
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp
      - /var/cache/nginx
      - /var/run

  redis:
    image: redis:7-alpine
    container_name: review-redis
    command: redis-server --appendonly yes --maxmemory 64mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 128M
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 3s
      retries: 3
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
    cap_drop: [ALL]

  # 可选：Dozzle 日志查看
  dozzle:
    image: amir20/dozzle:latest
    container_name: review-dozzle
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    ports:
      - "127.0.0.1:9999:8080"
    deploy:
      resources:
        limits:
          cpus: '0.1'
          memory: 32M
    restart: unless-stopped

volumes:
  redis_data:
    driver: local
```

### 目录结构

```
kais-review-platform/
├── docker-compose.yml
├── .env                    # JWT_SECRET 等敏感配置
├── .env.example            # 配置模板
├── .dockerignore
├── backend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
├── frontend/
│   └── dist/               # 构建产物
├── nginx/
│   └── nginx.conf
├── data/                   # SQLite 数据库（bind mount）
├── uploads/                # 上传文件
├── backup/                 # 备份目录
└── scripts/
    └── backup.sh
```

---

## 7. 总内存估算

| 服务 | 内存限制 | 预估实际占用 | 说明 |
|------|---------|-------------|------|
| API (Node.js) | 512M | 150-256M | 后端逻辑、SQLite 连接 |
| Nginx | 64M | 16-32M | 反代 + 静态文件 |
| Redis | 128M | 32-64M | 缓存、会话、队列 |
| Dozzle (可选) | 32M | 10-16M | 日志查看 |
| **合计** | **736M** | **~250-400M** | |

**结论：8GB RAM 完全够用，峰值占用不到 500MB，剩余 7.5GB+ 给系统和其他服务。**

---

## 8. 快速启动清单

```bash
# 1. 克隆并配置
cd kais-review-platform
cp .env.example .env
# 编辑 .env 设置 JWT_SECRET

# 2. 构建并启动
docker compose up -d --build

# 3. 检查状态
docker compose ps
docker compose logs -f api

# 4. 访问
# 前端: http://192.168.71.140
# API:  http://192.168.71.140/api/health
# 日志: http://localhost:9999 (Dozzle)

# 5. 备份（可选 cron）
# 0 * * * * /home/kai/kais-review-platform/scripts/backup.sh
```
