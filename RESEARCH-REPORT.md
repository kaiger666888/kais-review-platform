# kais-review-platform 调研报告

> 日期：2026-05-05 | 基于 Notion 架构设计文档深度调研

---

## 一、项目定位

为 AI 生产管线（kais-movie-agent、kais-gold-team 等）提供**审核/治理 API 服务**，Docker 化部署在低配机上，实现：
- 策略驱动的自动路由（AUTO/HUMAN/AI_AUDIT/BLOCK）
- 移动端优先的人工审核网关
- AI 审计预留接口（评分插件总线）
- 不可变审计日志链

---

## 二、推荐技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| **后端** | FastAPI (Python 3.12+) | 原生 async、内置 SSE、自动 OpenAPI 文档、与 kais-* Python 生态一致 |
| **数据库** | SQLite (WAL) + Redis 7 | SQLite 审计日志追加写入 + Redis 状态机/KV/过期策略，总 RAM < 50MB |
| **任务队列** | arq | 纯 async、Redis-based、与 FastAPI 共享事件循环，比 Celery 轻量 10x |
| **实时推送** | FastAPI 内置 SSE + httpx Webhook | 单向推送 SSE 足够，Webhook 用 httpx 异步发送 |
| **认证** | PyJWT | 短活 JWT（15min）+ 能力令牌，零依赖轻量实现 |
| **前端** | HTMX + Alpine.js + Tailwind CSS | 零构建、首屏快、14KB、服务端渲染，审核 CRUD 场景完美匹配 |
| **策略引擎** | OPA (Rego) 或 YAML 策略 | 声明式策略即代码，WASM 可嵌入，CNCF 毕业项目 |
| **部署** | Docker Compose (3 containers) | API + Redis + Nginx，总内存峰值 ~400MB |

### 资源估算

| 容器 | 镜像大小 | 运行时 RAM |
|---|---|---|
| App (FastAPI + SQLite) | ~120MB | 80-150MB |
| Redis 7 Alpine | ~30MB | 10-30MB |
| Nginx | ~10MB | ~10MB |
| **总计** | **~160MB** | **~100-190MB** |

---

## 三、竞品调研 Top 5

| 项目 | Stars | 核心参考价值 |
|---|---|---|
| **Cordum** | 新星 | 最直接对标：策略引擎 + 审批门 + 审计日志，YAML 策略即代码，risk-tier routing |
| **Temporal** | 11k+ | 状态机 + 持久化执行 + human signal，审核管线技术基座 |
| **OPA** | 9.5k+ | 策略引擎本身，Rego 声明式规则，WASM 嵌入 |
| **DeepEval** | 5k+ | AI 评分插件总线设计，可插拔评估指标 |
| **LangGraph** | 15k+ | 图状态机 + interrupt/resume + checkpoint |

---

## 四、可复用的设计模式

1. **Safety Kernel / Pre-execution Gate** — 每个审核对象执行前先过策略评估
2. **Graph State Machine + Checkpoint** — 审核流程建模为有向图，每个状态持久化
3. **Policy-as-Code** — 审核规则用 Rego/YAML 声明式定义，Git 版本化
4. **Pluggable Metric Plugin Bus** — AI 评分接口抽象为 Metric 接口，权重组合+阈值
5. **Risk-tier Routing** — 低风险自动通过，中风险 AI 审核，高风险人工审核
6. **Immutable Audit Trail** — Merkle Root 定期锚定到 Git
7. **Signal-based Human Approval** — 超时自动升级（AI 5min → 人工 24h）

---

## 五、部署方案

### Docker Compose 结构
```
review-platform/
├── docker-compose.yml
├── app/                  # FastAPI 应用
│   ├── Dockerfile
│   ├── main.py           # 入口 + arq worker 内嵌
│   ├── core/
│   │   ├── policy.py     # 策略引擎（OPA/YAML）
│   │   ├── checkpoint.py # 检查点状态机
│   │   ├── router.py     # 审批路由器
│   │   ├── token.py      # JWT + 能力令牌
│   │   ├── audit.py      # 审计记录器
│   │   └── events.py     # 事件总线 (SSE + Webhook)
│   ├── api/
│   │   ├── v1/
│   │   │   ├── review.py     # 审核提交/查询
│   │   │   ├── approval.py   # 审批操作
│   │   │   ├── policy.py     # 策略管理
│   │   │   └── audit.py      # 审计日志查询
│   ├── models/           # SQLAlchemy/SQLite
│   ├── templates/        # HTMX + Tailwind 模板
│   └── policies/         # Git 同步的策略文件
├── nginx/
│   ├── Dockerfile
│   └── nginx.conf        # 反代 SSE + 静态文件
└── data/                 # bind mount: SQLite + 策略文件
```

### 网络通信
- **低配机 IP**: 192.168.71.140
- kais-movie-agent / kais-gold-team → `POST http://192.168.71.140:8090/api/v1/review/submit`
- 审核平台 → 高配机 Webhook 回调
- 移动端 → `https://192.168.71.140:8090/` (PWA)

### 安全加固
- Docker: `read_only: true`, `cap_drop: ALL`, 非 root 用户
- JWT: 15min 短活令牌 + 一次性审核令牌
- Nginx: rate limiting, CORS 限制

---

## 六、与现有系统的集成点

| 接入方 | 集成方式 | 用途 |
|---|---|---|
| kais-movie-agent | REST API 提交审核 | 短剧渲染结果审核（图片/视频质量） |
| kais-gold-team | REST API + Webhook | GPU 任务放行（3090 高参渲染需审批） |
| Telegram/企微 | Webhook 通知 | 审核状态变更推送 |
| Git 仓库 | 定时拉取策略文件 | 策略版本化管理 |
| 未来 AI 评分 | 评分插件总线 | CLIP/美学模型自动审核 |

---

## 七、下一步

1. ✅ 调研完成
2. ⬜ 初始化项目骨架（FastAPI + SQLite + Redis）
3. ⬜ 实现策略引擎 + 检查点状态机
4. ⬜ 实现审核 API（submit/approve/reject）
5. ⬜ 实现 SSE 事件推送 + Webhook 通知
6. ⬜ 实现 PWA 审核前端（HTMX + Tailwind）
7. ⬜ Docker Compose 打包 + 部署测试
8. ⬜ 与 kais-movie-agent 集成测试
