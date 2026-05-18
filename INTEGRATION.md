# kais-review-platform 集成开发指导

> 来源: kais-aigc-integration 契约层
> 更新: 2026-05-18
> 状态: Phase 0-3 + 4B + 4C 已全部完成 (2026-05-18)

## Phase 0-3 完成状态

| Task | 状态 | 文件 |
|------|------|------|
| ApproveRequest.result 扩展 | ✅ | app/models/schemas.py (ReviewResult) |
| approve 存储 result | ✅ | app/api/v1/actions.py |
| 回调 payload 携带 result | ✅ | app/workers/tasks.py |
| movie-agent 策略文件 | ✅ | app/policies/movie_agent_phases.yaml (6 条规则) |
| 健康检查增强 | ✅ | app/main.py (/api/v1/health) |
| trace_id 接收存储 | ✅ | app/api/v1/reviews.py (X-Trace-Id) |

## 定位说明

**review-platform 是纯策略治理平台，不引入 LLM。**
- AI 评分（quality-gate、scene evaluation 等）由 movie-agent 自行完成
- review-platform 只负责：策略路由 (AUTO/HUMAN/BLOCK)、审核状态机、回调通知、审核 UI
- `NullScoringPlugin` 和 `shadow_score` 桩代码保持现状，不在本 repo 填充 LLM 逻辑

## Phase 4B — 审核体验增强 (✅ 已完成)

**实现**: Phase 23 (Review Template System) + Phase 24 (External Scoring Integration)

### 4B.1 [P1] 审核模板系统

**目标**: 按 source_system + phase 自定义审核 UI

**实现要点**:
- 模板定义：YAML/JSON 配置文件
- 渲染引擎：根据 review.metadata.phase 选择模板
- movie-agent 模板：候选图片并排 + 评分 + 选择按钮
- gold-team 模板：任务参数展示 + 风险评估

### 4B.2 [P1] quality-gate 接收外部评分

movie-agent 的 quality-gate phase 在本地完成 AI 评分后，将结果提交给 review-platform 存储：

```python
# movie-agent 提交审核时携带自评分数
POST /api/v1/reviews/
{
  "metadata": {
    "phase": "quality-gate",
    "ai_score": 72,                    # movie-agent 本地评分结果
    "ai_score_dimensions": {           # 各维度分数
      "visual_quality": 80,
      "audio_quality": 65,
      "consistency": 70
    },
    "ai_score_source": "movie-agent"   # 标明评分来源
  }
}
```

review-platform 只存储和展示这些分数，不自己计算。

### 4B.3 [P2] 外部评分展示

在审核详情页展示 movie-agent 提交的 AI 评分维度（只读展示，不调用 LLM）。

---

## Phase 4C — 可视化与运营 (✅ 已完成)

**实现**: Phase 25 (Analytics Dashboard)
**注**: 4C.2 PWA 移动端已在 Phase 21 (Mobile PWA) 中完成

### 4C.1 [P2] 审核数据分析 Dashboard

**指标**:
- 审核通过率（按 source_system、phase 分组）
- 平均等待时间
- AUTO/HUMAN 比例
- 外部评分分布（来自 movie-agent 的 ai_score）

### 4C.2 [P2] PWA 移动端

离线审核、推送通知、响应式优化。

### 4C.3 [P2] 批量审核

`BatchApproveRequest` 支持一次审核多个任务。

---

## 契约同步

review-platform API 契约:
- `/home/kai/workspace/kais-aigc-integration/contracts/review-platform-api.yaml`
- 回调 schema: `contracts/callback-schemas/review-callback.json`

## 任务优先级

| # | 任务 | 优先级 | 预估 | 状态 | Phase |
|---|------|--------|------|------|-------|
| 4B.1 | 审核模板系统 | P1 | 2 天 | ✅ | Phase 23 |
| 4B.2 | quality-gate 外部评分接收 | P2 | 0.5 天 | ✅ | Phase 24 |
| 4B.3 | 外部评分展示 | P2 | 1 天 | ✅ | Phase 24 |
| 4C.1 | 审核数据分析 Dashboard | P2 | 3 天 | ✅ | Phase 25 |
| 4C.2 | PWA 移动端 | P2 | 5 天 | ✅ | Phase 21 |
| 4C.3 | 批量审核 | P2 | 2 天 | ✅ | Phase 25 |
