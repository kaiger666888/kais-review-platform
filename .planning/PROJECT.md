# Kai's Review Platform

## What This Is

AI 生产管线审核治理平台，为 kais-movie-agent、kais-gold-team 等 AI 系统提供策略驱动的审核 API 服务。实现自动路由（AUTO/HUMAN/AI_AUDIT/BLOCK）、移动端人工审核网关、AI 审计接口预留和不可变审计日志链。

## Core Value

策略引擎驱动的审核路由 — 每个 AI 生产任务执行前必须通过策略评估，决定自动放行或进入人工审核，确保 AI 输出质量可控。

## Current State

**Shipped:** v1.1 Integration Tests & Tech Debt (2026-05-07)
**Status:** All v1.0 + v1.1 requirements validated. Platform fully tested end-to-end.
**Stats:** 7 phases, 18 plans, 7,145 LOC Python + 398 LOC Bash, 170 tests passing

## Current Milestone: v1.2 External System Integration

**Goal:** 将 kais-gold-team 和 kais-movie-agent 接入审核平台，实现 Telegram + 移动端双通道审核，审批通过后全自动回调恢复执行。

**Target features:**
1. Review Platform Telegram Bot — 新建独立 Telegram Bot，接收审核通知，提供 InlineKeyboard 审批按钮
2. kais-gold-team 审核拦截 — control_node 在 GPU 任务调度前提交审核，高风险走 HUMAN，低风险 AUTO 放行，审批通过后回调自动继续执行
3. kais-movie-agent 审核门替换 — 替换 `interactive-review.js` 本地审核为 review-platform API 调用，7 个制作阶段的审核门接入远程审核
4. 双 Bot 协作 — gold-team Bot 转发审核请求到 review-platform Bot，统一审批入口
5. 全回调自动化 — 审批通过 → webhook 回调 kais-* → 自动恢复 pipeline/guardian 执行

## Requirements

### Validated

- ✓ 策略引擎支持 YAML 声明式规则，按风险等级自动路由（AUTO/HUMAN/AI_AUDIT/BLOCK） — v1.0 Phase 01
- ✓ 审核流程建模为有向图状态机，支持检查点持久化和恢复 — v1.0 Phase 01
- ✓ REST API 支持提交审核（submit）、审批（approve/reject）、查询（query） — v1.0 Phase 01
- ✓ SSE 实时推送审核状态变更 + httpx Webhook 回调通知 — v1.0 Phase 02
- ✓ JWT 认证（短活令牌 15min）+ 一次性审核令牌（32 字符不可猜测） — v1.0 Phase 01
- ✓ 不可变审计日志，支持查询和追溯 — v1.0 Phase 01
- ✓ 移动端优先的审核前端（HTMX + Alpine.js + Tailwind CSS） — v1.0 Phase 03
- ✓ Docker Compose 4 容器部署（API + Nginx + Redis + 可选 Dozzle），总内存 < 400MB — v1.0 Phase 04
- ✓ 与 kais-movie-agent 集成（REST + Webhook） — v1.0 Phase 02
- ✓ 与 kais-gold-team 集成（REST + Webhook） — v1.0 Phase 02
- ✓ AI 评分插件总线接口预留（CLIP/美学模型） — v1.0 Phase 01

### Active

- [ ] Review Platform Telegram Bot 接收审核通知，InlineKeyboard 审批
- [ ] kais-gold-team GPU 任务审核拦截（control_node 提交审核 → 策略路由 → 回调自动恢复）
- [ ] kais-movie-agent 7 个制作阶段审核门替换为远程审核 API 调用
- [ ] 双 Bot 协作（gold-team Bot → review-platform Bot）
- [ ] 全回调自动化闭环（审批 → webhook → kais-* 自动恢复执行）

### Validated in v1.1

- ✓ API 端到端集成测试覆盖所有核心流程 — v1.1 Phase 06
- ✓ SSE 实时推送集成测试 — v1.1 Phase 06
- ✓ Webhook 投递 + 重试集成测试 — v1.1 Phase 06
- ✓ Docker Compose 全栈黑盒测试 — v1.1 Phase 07
- ✓ create_review_token 端点补全 — v1.1 Phase 05
- ✓ Web 模板路由认证修复 — v1.1 Phase 05
- ✓ audit_protect_authorizer 注册修复 — v1.1 Phase 05

### Out of Scope

- OPA/Rego 策略引擎 — v1 使用 YAML 策略，降低复杂度
- 实时 WebSocket 双向通信 — SSE 单向推送足够
- Prometheus/Grafana 监控 — 太重，v1 用 Docker 原生 + 简单脚本
- OAuth/第三方登录 — v1 仅 JWT
- 多租户支持 — 单用户/单团队场景
- 移动原生 App — PWA 优先
- 视频流式审核 — v1 仅处理预览图/缩略图

## Context

- 部署环境：低配机 192.168.71.140（8-16GB RAM），高配机 Worker 192.168.71.38
- kais-movie-agent：短剧 AI 渲染系统，需要审核场景图/分镜质量
- kais-gold-team：GPU 任务调度系统，3090 高参渲染需要审批放行
- 竞品参考：Cordum（策略+审批+审计）、Temporal（状态机）、LangGraph（图状态机+checkpoint）
- 设计模式：Safety Kernel、Policy-as-Code、Risk-tier Routing、Signal-based Human Approval
- v1.0 已归档：4 phase, 12 plans, 109 单元测试通过
- v1.1 已归档：3 phases, 6 plans, 30 集成测试 + 398 行 Docker 黑盒测试脚本，3 技术债修复
- 当前：170 tests passing，7,145 LOC Python + 398 LOC Bash
- 技术债：aiosqlite set_authorizer best-effort 注册（低影响，应用层为主要防护）

## Constraints

- **资源限制**: 目标机器 8-16GB RAM，Docker 容器总内存 < 400MB
- **技术栈**: FastAPI (Python 3.12+) + SQLite (WAL) + Redis 7 + HTMX + Alpine.js + Tailwind CSS
- **网络**: 局域网部署，无公网，API 地址 http://192.168.71.140:8090
- **数据库**: SQLite 单进程写入，WAL 模式，bind mount 持久化
- **任务队列**: arq（纯 async，Redis-based，不使用 Celery）
- **前端**: 零构建步骤，服务端渲染（HTMX），总 bundle < 50KB
- **安全**: Docker read_only + cap_drop ALL + non-root 用户

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI over Node.js | 原生 async、内置 SSE、自动 OpenAPI 文档、与 kais-* Python 生态一致 | ✓ Good |
| SQLite over PostgreSQL | 审计日志追加写入场景、总 RAM < 50MB、单机部署无需分布式 DB | ✓ Good |
| YAML 策略 over OPA/Rego | 降低 v1 复杂度，YAML 可读性好，满足需求 | ✓ Good |
| HTMX over React/Vue | 审核 CRUD 场景完美匹配、零构建、14KB bundle、服务端渲染 | ✓ Good |
| arq over Celery | 纯 async、轻量 10x、与 FastAPI 共享事件循环 | ✓ Good |
| SSE over WebSocket | 单向推送足够、FastAPI 原生支持、无需额外依赖 | ✓ Good |
| redis 5.3.1 not 7.4.0 | arq 0.28.0 dependency constraint (redis<6) | ✓ Good |
| SSE async generator pattern (FastAPI 0.136) | Endpoint must be async generator with response_class=EventSourceResponse, NOT function returning EventSourceResponse | ✓ Good (discovered in v1.1 Phase 06) |
| Session-per-request for SQLite tests | Each API request gets its own AsyncSession to avoid re-entrant commit conflicts | ✓ Good |
| Patch emit_state_change for integration tests | SSE/webhook tested separately, avoids async_session_factory conflicts | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-07 after v1.2 milestone started*
