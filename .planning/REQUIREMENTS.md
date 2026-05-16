# Requirements: Kai's Review Platform V2

**Defined:** 2026-05-16
**Core Value:** Shot Card 是审核原子 — 将 OpenClaw 节点拓扑折叠为叙事分镜单元，捆绑首帧/尾帧/视频/音频/提示词，实现一体化审核

## v2.0 Requirements

### Shot Card Core (SHOT)

- [ ] **SHOT-01**: Shot Card 数据模型定义，包含 shot_id, project_id, narrative_context (scene, shot_number, emotion_curve, continuity_tags), visual_bundle (keyframes, video_clip, prompt, candidates), audio_bundle (bgm_prompt, sfx_prompt, status), audit_state (status, routing_decision, min_audit_set, blocking_reason), provenance (workflow_version, policy_commit_sha, execution_id)
- [x] **SHOT-02**: Shot Card 聚合器 — 监听 OpenClaw 事件总线，按 shot_id 渐进式聚合节点输出到对应 Shot Card
- [x] **SHOT-03**: 拓扑折叠器 — 将 OpenClaw DAG 节点输出映射到 Shot Card bundles，处理乱序完成（video before image）
- [x] **SHOT-04**: 渐进式填充 — visual_bundle 先完成先显示，audio_bundle 完成后自动附加，min_audit_set 就绪后解锁审核按钮

### Policy & GitOps (POL)

- [ ] **POL-01**: 策略引擎增强 — 接受 Shot Card 作为输入（非 flat dict），支持策略叠加（全局+项目+临时策略），narrative_context 感知
- [ ] **POL-02**: GitOps 策略即代码 — 策略文件入 Git repo，PR 审批变更，运行时读取 policy_commit_sha
- [ ] **POL-03**: Provenance 追踪 — 每个 Shot Card 携带 workflow_version, policy_commit_sha, execution_id，审计记录关联策略版本

### Routing & Tokens (ROUT)

- [ ] **ROUT-01**: 审批路由器 — 根据策略引擎输出动态分流到三个出口（桌面/移动/AI），优先级队列（高参渲染高优、抽卡预览低优），批量审批
- [x] **ROUT-02**: 能力令牌（Capability Token） — 审核通过后发放，OpenClaw 执行层校验令牌后才允许高成本 GPU 任务执行

### Checkpoint & Events (CHKP)

- [x] **CHKP-01**: 检查点管理器 — 将 OpenClaw 运行状态序列化为 RunState Snapshot 存入 Redis，审核通过后注入 ResumeCommand 恢复执行
- [x] **CHKP-02**: 分级超时策略 — 人工审核默认 24h 超时转拒绝，AI 审核 5min 超时转人工
- [x] **EVT-01**: 事件总线增强 — 渐进式填充事件（node_completed, bundle_ready, shot_card_updated），per-outlet 路由

### Database & Storage (DB)

- [ ] **DB-01**: PostgreSQL + TimescaleDB 迁移 — 替换 SQLite，hypertable 配置审计数据，asyncpg 驱动
- [x] **DB-02**: 分层存储架构 — 热存储 PostgreSQL (30d), 温存储 MinIO JSONL (1yr), 冷存储 WORM (永久)
- [x] **DB-03**: 数据生命周期管理 — arq cron 自动归档 worker，可配置保留策略
- [ ] **DB-04**: Docker Compose 扩展 — PostgreSQL 容器 (~200MB) + MinIO 容器 (~128MB)，总内存 < 1GB

### Desktop Workstation (UI-D)

- [x] **UI-D-01**: 三栏工作台布局 — 左栏分镜队列（项目/场次/风险筛选）、中栏 Shot Card 预览（视频播放器/帧查看器/候选阵列）、右栏决策面板（叙事上下文/提示词/节点状态/决策按钮）
- [ ] **UI-D-02**: 键盘快捷键 — Space 播放/暂停, Y/N 通过/拒绝, J/K 切换 Shot, D Diff 对比, B 批量, G Git 策略, L 日志
- [ ] **UI-D-03**: 双栏对比 — 首帧 vs 尾帧, 当前候选 vs 历史版本, 当前 vs 参考图
- [ ] **UI-D-04**: 批量操作 — Ctrl/Shift 多选左栏 Shot，一键批量决策（通过/拒绝/挂起）
- [x] **UI-D-05**: 候选阵列 — 同一 Shot 多抽卡结果缩略图阵列，点击无缝切换

### Mobile PWA (UI-M)

- [x] **UI-M-01**: 卡片流布局 — 纵向滑动切换分镜（叙事连续性），横向滑动切换候选，首帧/尾帧始终可见
- [x] **UI-M-02**: 手势操作 — 左滑通过、右滑拒绝、上滑详情、双指放大
- [x] **UI-M-03**: 上下文条 — 卡片顶部显示场次、镜头编号、情绪曲线
- [x] **UI-M-04**: PWA 离线缓存 — Service Worker 缓存最近 20 条 Shot Card, manifest.json
- [x] **UI-M-05**: 移动端 API — Shot Card bundles 接口，分镜逐条分页，渐进加载

### AI Audit (AI)

- [x] **AI-01**: AI 审计 Phase 0 — 评分插件总线返回空向量（美学/一致性/合规/技术质量/音频匹配度），路由 fallback 到人工
- [x] **AI-02**: 影子模式 — AI 评分持续运行但不影响决策，记录结果用于训练
- [x] **AI-03**: 模型注册中心（占位） — 空注册表，标记 model_unavailable
- [x] **AI-04**: 反馈闭环（占位） — 人工审核结果入冷存储，作为未来训练信号
- [x] **AI-05**: A/B 测试接口（占位） — 预留数据格式，同一批 Shot Card 并行送 AI 和人工

### Audit & Compliance (AUDIT)

- [x] **AUDIT-01**: Merkle Root 锚定 — 每日审计日志 Merkle Root 写入 Git，防篡改校验
- [x] **AUDIT-02**: 双写审计记录器 — 实时写入 PostgreSQL + 异步归档到 MinIO
- [ ] **AUDIT-03**: 桌面审计驾驶舱 — 时间轴视图、统计面板（吞吐量/拒绝原因/策略命中）、策略版本 Diff 模式
- [ ] **AUDIT-04**: 移动端审计页 — Dashboard 统计、瀑布流审核历史、详情页

### Media Preview (MEDIA)

- [ ] **MEDIA-01**: 视频播放基础设施 — 视频流端点、帧提取、时间轴控制
- [ ] **MEDIA-02**: 缩略图生成 — 首帧/尾帧/候选缩略图自动生成
- [ ] **MEDIA-03**: 候选对比视图 — 多抽卡候选并排/叠加对比

### Authentication & Config (AUTH)

- [x] **AUTH-01**: 多角色认证 — admin (策略管理), reviewer (桌面/移动), auditor (只读分析), ai_service (评分)
- [ ] **AUTH-02**: 配置扩展 — git_repo_url, postgres_url, minio_endpoint, openclaw_event_url, capability_token_secret, 保留策略设置
- [ ] **AUTH-03**: 依赖更新 — 添加 asyncpg, gitpython, minio; 移除 aiosqlite

## Out of Scope

| Feature | Reason |
|---------|--------|
| AI Phase 1-4 自动化 | V2 仅 Phase 0（全人工 + 预留窗口），AI 评分能力未就绪 |
| OpenClaw 深度集成 | 依赖外部 OpenClaw API 可用性，V2 仅定义接口和 mock |
| 移动原生 App | PWA 优先，原生 App 成本过高 |
| OAuth/第三方登录 | JWT 足够 |
| 多租户 | 单团队场景 |
| Prometheus/Grafana | V2 审计驾驶舱覆盖监控需求 |
| CDN/公网部署 | 局域网 only |
| 视频流式审核（逐帧标注） | V2 仅支持视频播放和关键帧查看 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SHOT-01 | Phase 15 | Pending |
| DB-01 | Phase 15 | Pending |
| DB-04 | Phase 15 | Pending |
| AUTH-02 | Phase 15 | Pending |
| AUTH-03 | Phase 15 | Pending |
| SHOT-02 | Phase 16 | Complete |
| SHOT-03 | Phase 16 | Complete |
| SHOT-04 | Phase 16 | Complete |
| POL-01 | Phase 17 | Pending |
| POL-02 | Phase 17 | Pending |
| POL-03 | Phase 17 | Pending |
| ROUT-01 | Phase 18 | Pending |
| CHKP-01 | Phase 18 | Complete |
| CHKP-02 | Phase 18 | Complete |
| EVT-01 | Phase 18 | Complete |
| ROUT-02 | Phase 19 | Complete |
| AI-01 | Phase 19 | Complete |
| AI-02 | Phase 19 | Complete |
| AI-03 | Phase 19 | Complete |
| AI-04 | Phase 19 | Complete |
| AI-05 | Phase 19 | Complete |
| UI-D-01 | Phase 20 | Complete |
| UI-D-02 | Phase 20 | Pending |
| UI-D-03 | Phase 20 | Pending |
| UI-D-04 | Phase 20 | Pending |
| UI-D-05 | Phase 20 | Complete |
| MEDIA-01 | Phase 20 | Pending |
| MEDIA-02 | Phase 20 | Pending |
| MEDIA-03 | Phase 20 | Pending |
| UI-M-01 | Phase 21 | Complete |
| UI-M-02 | Phase 21 | Complete |
| UI-M-03 | Phase 21 | Complete |
| UI-M-04 | Phase 21 | Complete |
| UI-M-05 | Phase 21 | Complete |
| AUDIT-01 | Phase 22 | Complete |
| AUDIT-02 | Phase 22 | Complete |
| AUDIT-03 | Phase 22 | Pending |
| AUDIT-04 | Phase 22 | Pending |
| AUTH-01 | Phase 22 | Complete |
| DB-02 | Phase 22 | Complete |
| DB-03 | Phase 22 | Complete |

**Coverage:**
- v2.0 requirements: 42 total
- Mapped to phases: 42
- Unmapped: 0

---
*Requirements defined: 2026-05-16*
*Last updated: 2026-05-16 after V2 roadmap creation*
