# Kai's Review Platform V2

## What This Is

AI 短剧管线治理平台（OpenClaw 治理层），为 kais-movie-agent、kais-gold-team 等 AI 系统提供 Shot Card 驱动的审核治理。通过 GitOps 版本控制、策略引擎路由、桌面三栏工作台 + 移动 PWA 卡片流双端审核、AI 审计预留窗口，为短剧管线提供可审计、可回溯、可渐进自动化的质量闸门。

## Core Value

Shot Card 是审核原子 — 将 OpenClaw 节点拓扑折叠为叙事分镜单元，捆绑首帧/尾帧/视频/音频/提示词，实现"时空-视听"一体化审核，确保每个分镜在进入高成本下游执行前通过质量闸门。

## Current State

**V1 已归档:** v1.0-v1.2（12 phases, 28 plans, 266 tests passing）
**V2 启动:** 全量重写，从通用审核队列重构为 Shot Card 驱动的管线治理平台
**V2 架构文档:** `.planning/research/V2-ARCHITECTURE.md`
**差距分析:** `.planning/research/V2-GAP-ANALYSIS.md`

## Current Milestone: v2.0 Architecture Rewrite

**Goal:** 全量重写为 V2 架构。四大架构层（GitOps 版本控制、治理核心引擎、审核出口、审计数据展示），15+ 新组件，Shot Card 数据模型替换 Review 模型。

## Requirements

### Validated

<!-- V1 capabilities that carry forward into V2 -->

- ✓ 策略引擎 YAML 声明式规则，按风险等级自动路由（AUTO/HUMAN/AI_AUDIT/BLOCK） — v1.0
- ✓ 有向图状态机，乐观锁并发控制 — v1.0
- ✓ REST API 完整 CRUD — v1.0
- ✓ SSE 实时推送 + Webhook 回调 — v1.0
- ✓ JWT 认证 + 一次性审核令牌 — v1.0
- ✓ SHA-256 哈希链不可变审计日志 — v1.0
- ✓ Docker Compose 部署 — v1.0
- ✓ 与 kais-gold-team / kais-movie-agent 集成 — v1.2

### Active

- [ ] **SHOT-01**: Shot Card 数据模型（shot_id, project_id, narrative_context, visual_bundle, audio_bundle, audit_state, provenance）
- [ ] **SHOT-02**: Shot Card 聚合器 — 监听 OpenClaw 事件，按 shot_id 渐进式聚合节点输出
- [ ] **SHOT-03**: 拓扑折叠器 — 将 OpenClaw DAG 节点输出映射到 Shot Card bundles
- [ ] **SHOT-04**: 渐进式填充 — 视觉 bundle 先完成先显示，音频完成后附加，min_audit_set 解锁审核
- [ ] **POL-01**: 策略引擎增强 — Shot Card 作为输入（非 flat dict），策略叠加（全局+项目+临时）
- [ ] **POL-02**: GitOps 策略即代码 — 策略文件入 Git，PR 审批，运行时读取 commit SHA
- [ ] **POL-03**: Provenance 追踪 — 每个 Shot Card 记录 workflow_version, policy_commit_sha, execution_id
- [ ] **ROUT-01**: 审批路由器 — 动态分流到三个出口（桌面/移动/AI），优先级队列，批量审批
- [ ] **ROUT-02**: 能力令牌（Capability Token） — 审批通过后发放，OpenClaw 执行层校验
- [ ] **CHKP-01**: 检查点管理器 — RunState Snapshot 序列化到 Redis，ResumeCommand 注入
- [ ] **EVT-01**: 事件总线增强 — 渐进式填充事件、per-outlet 路由、node_completed/bundle_ready 事件类型
- [ ] **AUDIT-01**: Merkle Root 锚定 — 每日审计日志 Merkle Root 写入 Git
- [ ] **AUDIT-02**: 双写审计 — 实时写入 PostgreSQL + 异步归档到对象存储
- [ ] **DB-01**: PostgreSQL + TimescaleDB 替换 SQLite — 热存储 30 天滚动
- [ ] **DB-02**: 分层存储 — 热(PostgreSQL 30d) / 温(MinIO JSONL 1yr) / 冷(WORM 永久)
- [ ] **DB-03**: 数据生命周期管理 — 自动归档 worker，可配置保留策略
- [ ] **UI-D-01**: 桌面三栏工作台 — 左栏分镜队列、中栏 Shot Card 预览（视频/帧/候选阵列）、右栏决策面板
- [ ] **UI-D-02**: 桌面键盘快捷键 — Space/Y/N/J/K/B/D/G/L 全键盘操作
- [ ] **UI-D-03**: 桌面双栏对比 — 首帧 vs 尾帧、候选 vs 历史版本、当前 vs 参考图
- [ ] **UI-D-04**: 桌面批量操作 — Ctrl/Shift 多选批量决策
- [ ] **UI-M-01**: 移动 PWA 卡片流 — 纵向切换分镜、横向切换候选、手势操作
- [ ] **UI-M-02**: 移动 PWA 离线缓存 — Service Worker 缓存最近 20 条 Shot Card
- [ ] **AI-01**: AI 审计 Phase 0 — 评分插件总线返回空向量，路由 fallback 到人工，影子模式记录
- [ ] **AI-02**: AI 审计接口预留 — 模型注册中心、反馈闭环、A/B 测试、熔断机制
- [ ] **MEDIA-01**: 媒体预览基础设施 — 视频播放、帧提取、缩略图、候选对比

### Out of Scope

- AI Phase 1-4 自动化审计 — V2 仅实现 Phase 0（全人工 + 预留窗口）
- OpenClaw 深度集成（GAP-CC.1） — 依赖外部 OpenClaw 系统 API 可用性，V2 仅定义接口
- 移动原生 App — PWA 优先
- OAuth/第三方登录 — JWT 足够
- 多租户 — 单团队场景
- CDN/公网部署 — 局域网 only

## Context

- V2 架构设计文档来自 Notion，已保存至 `.planning/research/V2-ARCHITECTURE.md`
- 24 个差距已识别，详见 `.planning/research/V2-GAP-ANALYSIS.md`
- 9 个 V1 组件可扩展复用（状态机、策略引擎、审计日志、事件管理、令牌服务、Webhook 投递、超时管理、Gold Team 客户端、Telegram Bot）
- OpenClaw 是短剧管线的执行引擎，治理层作为其审核闸门
- Shot Card 概念将审核粒度从"单张图/单段视频"提升到"叙事分镜"
- 内存约束从 400MB 放宽到 1GB（PostgreSQL ~200MB + MinIO ~128MB + API 256MB + Redis 64MB + Nginx 32MB）
- 部署环境：192.168.71.140（8-16GB RAM），局域网

## Constraints

- **资源限制**: 目标机器 8-16GB RAM，Docker 容器总内存 < 1GB
- **技术栈**: FastAPI (Python 3.12+) + PostgreSQL (TimescaleDB) + Redis 7 + HTMX/Alpine.js/Tailwind CSS + MinIO
- **网络**: 局域网部署，无公网，API 地址 http://192.168.71.140:8090
- **数据库**: PostgreSQL + TimescaleDB，热温冷分层存储
- **任务队列**: arq（纯 async，Redis-based）
- **前端**: 桌面三栏工作台（HTMX SSR），移动 PWA（卡片流），零构建步骤
- **安全**: Docker read_only + cap_drop ALL + non-root 用户
- **GitOps**: 所有决策逻辑入 Git，运行时读取 commit SHA

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 全量重写（非渐进迁移） | V2 Shot Card 数据模型与 V1 Review 结构根本不同，渐进迁移成本更高 | — Pending |
| PostgreSQL 替换 SQLite | V2 需要复杂查询、时序分析、分区；SQLite 单进程写入成为瓶颈 | — Pending |
| 内存约束放宽到 1GB | PostgreSQL (~200MB) + MinIO (~128MB) 无法容纳在 400MB 内；8GB 机器足够 | — Pending |
| HTMX 桌面三栏 + PWA 移动端 | 桌面追求效率（键盘/对比/批量），移动追求可用性（手势/离线/叙事连续性） | — Pending |
| AI 审计 Phase 0 only | AI 评分能力未就绪，先建立预留接口，影子模式收集数据 | — Pending |
| MinIO 替代 S3 | 局域网部署无公网，MinIO 提供 S3 兼容接口 | — Pending |
| 保留 Telegram Bot | 作为审核通知补充通道（非主审核入口），V2 主入口为桌面/移动网关 | — Pending |

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
*Last updated: 2026-05-16 after V2 project initialization*
