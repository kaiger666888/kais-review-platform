# Phase 25: Analytics Dashboard - Research

**Researched:** 2026-05-18
**Domain:** Review data analytics dashboard (throughput, approval rates, score distributions, batch review enhancements)
**Confidence:** HIGH

## Summary

Phase 25 构建 V2 审核数据分析仪表板，覆盖 INTEGRATION.md 的 Phase 4C.1（审核数据分析 Dashboard）和 4C.3（批量审核）。核心任务是：(1) 新增 `/analytics` 页面展示按 source_system 和 phase 分组的通过率、平均等待时间、AUTO/HUMAN 路由比例、外部评分分布；(2) 增强 BatchApproveRequest 以支持单次操作审核多个任务并生成完整审计轨迹。

关键发现：现有 `audit_cockpit.html` 已有三栏审计驾驶舱（Timeline + Statistics + Policy Diff），其中 `_audit_stats.html` 已渲染总决策数、通过率、平均决策时间、每日吞吐量柱状图、拒绝原因和策略命中。但该驾驶舱仅查询 V1 AuditEntry 表，不区分 source_system/phase 维度，不展示 AUTO/HUMAN 路由比例，不展示外部评分分布。V2 ShotCard 模型有独立的 `routing_decision`（AUTO/HUMAN/AI_AUDIT/BLOCK）和 `audit_status`（awaiting_audit/approved/rejected）字段，为路由比例和评分分布提供了数据源。

BatchApproveRequest 已存在于 `app/models/schemas.py`（支持 1-100 个 review_ids + 可选 comment），API 端点 `/api/v1/reviews/batch/approve` 和 `/batch/reject` 已完整实现，返回 207 Multi-Status + BatchResponse。Workstation 的批量审核也已实现（`batch_approve_shot_cards_htmx`），但 V1 批量操作没有前端入口——需要补充 Web UI 入口。

**Primary recommendation:** 复用现有 audit stats 查询模式，扩展为按 source_system/phase 分组的聚合查询；新增 `/analytics` 页面或扩展现有 audit cockpit 的 statistics 面板；利用 ShotCard.routing_decision 统计 AUTO/HUMAN 比例；利用 narrative_context JSONB 中的 ai_score 统计评分分布。BatchApproveRequest 的 API 层已完整，主要需要补充 Web UI 入口和 HTMX partial。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 审核聚合查询 | API / Backend | -- | SQLAlchemy 聚合查询 AuditEntry + Review + ShotCard，返回统计数据 |
| source_system/phase 分组 | API / Backend | -- | GROUP BY 聚合逻辑在 SQL 层完成，前端消费结果 |
| AUTO/HUMAN 路由比例 | API / Backend | -- | 查询 ShotCard.routing_decision 或 Review.disposition 聚合 |
| AI 评分分布 | API / Backend | -- | 从 ShotCard.narrative_context JSONB 提取 ai_score 聚合 |
| Dashboard 页面渲染 | Frontend Server (SSR) | Browser / Client | Jinja2 服务端渲染仪表板页面 + HTMX 局部刷新 |
| 交互式图表 | Browser / Client | Frontend Server (SSR) | CSS 柱状图/进度条（与现有 daily throughput bar 一致），Alpine.js 交互 |
| 批量审核 UI | Frontend Server (SSR) | Browser / Client | HTMX 表单提交到现有 batch API |
| 批量审核 API | API / Backend | -- | 已实现（actions.py），返回 207 Multi-Status |

## Standard Stack

### Core

No new packages required. Phase uses existing stack entirely:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136 | Analytics API endpoints | Existing router pattern, async handlers [VERIFIED: requirements.txt] |
| SQLAlchemy | 2.0.49 | Aggregation queries | GROUP BY, JSONB extraction, func.count/avg [VERIFIED: requirements.txt] |
| Jinja2 | 3.1.6 | Dashboard page rendering | Server-side rendering with existing template system [VERIFIED: codebase] |
| HTMX | 2.0.9 | Dashboard partial refresh | Date range filter, tab switching [VERIFIED: codebase] |
| Alpine.js | 3.15.12 | Interactive chart state | Tab switching, score distribution toggle [VERIFIED: codebase] |
| Tailwind CSS | 4.2.3 | Dashboard layout | Grid layout for metric cards, chart bars [VERIFIED: codebase] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| jinja2-fragments | 1.8.0 | Partial template rendering | HTMX partial responses for dashboard sections |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| CSS-based bar charts (existing pattern) | Chart.js / Apache ECharts | Adding a charting library adds build dependency and bundle size. Existing CSS bar pattern in `_audit_stats.html` works well for throughput/approval rate bars. Score distribution histogram can use the same pattern. |
| Standalone `/analytics` page | Extend audit cockpit | Audit cockpit is role-restricted (auditor/admin). Analytics dashboard should be accessible to all authenticated users. Separate page is cleaner. |
| Dedicated analytics API | Extend existing `/api/v1/audit/stats` | Existing stats endpoint already does heavy lifting. But it only queries AuditEntry, not ShotCard. Analytics dashboard needs cross-model queries. New endpoint is cleaner. |

**Installation:**
```bash
# No new packages required
```

## Package Legitimacy Audit

No new packages are installed in this phase. All dependencies are already in requirements.txt.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (none) | -- | -- | -- | -- | -- | N/A |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │         Analytics Dashboard Page            │
                    │         /analytics (Jinja2 SSR)            │
                    │  ┌─────────┬──────────┬──────────────────┐ │
                    │  │ Metric  │ Charts   │ Score            │ │
                    │  │ Cards   │ (CSS bar)│ Distribution     │ │
                    │  └────┬────┴─────┬────┴────────┬─────────┘ │
                    │       │          │             │            │
                    └───────┼──────────┼─────────────┼────────────┘
                            │ HTMX     │ HTMX       │ HTMX
                            ▼          ▼             ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                                    │
│                                                                       │
│  GET /api/v1/analytics/summary                                        │
│  ┌──────────────────────────────────────────────────┐                 │
│  │  Query AuditEntry + Review (V1 path)             │                 │
│  │  GROUP BY source_system, phase                   │                 │
│  │  -> approval_rate, avg_wait_time, throughput     │                 │
│  └──────────────────────────────────────────────────┘                 │
│                                                                       │
│  GET /api/v1/analytics/routing-ratio                                  │
│  ┌──────────────────────────────────────────────────┐                 │
│  │  Query ShotCard.routing_decision                  │                 │
│  │  GROUP BY routing_decision                        │                 │
│  │  -> AUTO/HUMAN/AI_AUDIT/BLOCK counts              │                 │
│  └──────────────────────────────────────────────────┘                 │
│                                                                       │
│  GET /api/v1/analytics/score-distribution                             │
│  ┌──────────────────────────────────────────────────┐                 │
│  │  Query ShotCard.narrative_context JSONB           │                 │
│  │  WHERE ai_score IS NOT NULL                       │                 │
│  │  -> score histogram buckets                       │                 │
│  └──────────────────────────────────────────────────┘                 │
│                                                                       │
│  POST /api/v1/reviews/batch/approve (already exists)                  │
│  POST /api/v1/reviews/batch/reject  (already exists)                  │
│  ┌──────────────────────────────────────────────────┐                 │
│  │  Accept BatchApproveRequest (1-100 review_ids)    │                 │
│  │  transition_state per review with audit trail     │                 │
│  │  Return 207 Multi-Status                          │                 │
│  └──────────────────────────────────────────────────┘                 │
└───────────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────┐          ┌──────────────────────┐
│  PostgreSQL       │          │  Review + AuditEntry  │
│  ShotCard table   │          │  tables (V1)          │
│  (V2 data)        │          │                       │
│  - routing_decision│         │  - source_system      │
│  - narrative_context│        │  - disposition        │
│    (ai_score)     │          │  - state transitions  │
└──────────────────┘          └──────────────────────┘
```

### Recommended Project Structure

```
app/
├── api/v1/
│   ├── analytics.py           # NEW: Analytics aggregation endpoints
│   └── actions.py             # EXISTING: Batch approve/reject (no change needed)
├── templates/
│   ├── pages/
│   │   └── analytics.html     # NEW: Analytics dashboard page
│   └── partials/
│       ├── _analytics_metrics.html    # NEW: Metric cards (throughput, rate, wait time)
│       ├── _analytics_by_source.html  # NEW: Grouped by source_system table/chart
│       ├── _analytics_by_phase.html   # NEW: Grouped by phase table/chart
│       ├── _analytics_routing.html    # NEW: AUTO/HUMAN ratio pie/bar
│       └── _analytics_scores.html     # NEW: AI score distribution histogram
├── web/
│   └── routes.py              # EXTEND: Add /analytics route + HTMX partials
└── models/
    └── schemas.py             # EXISTING: BatchApproveRequest (no change)
```

### Pattern 1: Reuse Existing Audit Stats Query Pattern

**What:** The `audit_stats_partial` route handler in `routes.py` (lines 634-753) already demonstrates the exact query pattern needed: date range filtering, count aggregation, approval/rejection breakdown, daily throughput grouping. Extend this pattern with GROUP BY source_system/phase.

**When to use:** All analytics aggregation queries.

**Example:**

```python
# Source: [CITED: app/web/routes.py audit_stats_partial]

# Existing pattern (flat aggregation):
total_result = await session.execute(
    select(func.count()).select_from(AuditEntry)
    .where(
        AuditEntry.action.in_(["approve", "reject"]),
        AuditEntry.created_at >= start_dt,
        AuditEntry.created_at <= end_dt,
    )
)

# Extended pattern (grouped by source_system + phase):
from sqlalchemy import case

grouped_result = await session.execute(
    select(
        Review.source_system,
        # Extract phase from metadata JSONB
        func.json_extract_path_text(Review.metadata_json, "phase").label("phase"),
        func.count().label("total"),
        func.sum(case((AuditEntry.action == "approve", 1), else_=0)).label("approved"),
        func.sum(case((AuditEntry.action == "reject", 1), else_=0)).label("rejected"),
    )
    .join(AuditEntry, AuditEntry.review_id == Review.id)
    .where(
        AuditEntry.action.in_(["approve", "reject"]),
        AuditEntry.created_at >= start_dt,
        AuditEntry.created_at <= end_dt,
    )
    .group_by(Review.source_system, "phase")
    .order_by(Review.source_system, "phase")
)
```

### Pattern 2: JSONB Extraction for Score Distribution

**What:** Extract `ai_score` from `ShotCard.narrative_context` JSONB and bucket into histogram ranges. Phase 24 already stores `ai_score` in `narrative_context`.

**When to use:** Score distribution visualization.

**Example:**

```python
# Source: [CITED: app/models/shot_card.py narrative_context JSONB]
# Score distribution query
score_result = await session.execute(
    select(
        func.count().label("count"),
        case(
            (ShotCard.narrative_context["ai_score"].astext.cast(Integer) >= 90, "90-100"),
            (ShotCard.narrative_context["ai_score"].astext.cast(Integer) >= 70, "70-89"),
            (ShotCard.narrative_context["ai_score"].astext.cast(Integer) >= 50, "50-69"),
            (ShotCard.narrative_context["ai_score"].astext.cast(Integer) >= 30, "30-49"),
            else_="0-29",
        ).label("bucket"),
    )
    .where(
        ShotCard.narrative_context["ai_score"].astext.isnot(None),
        ShotCard.created_at >= start_dt,
        ShotCard.created_at <= end_dt,
    )
    .group_by("bucket")
)
```

### Pattern 3: CSS Bar Chart (Existing Pattern)

**What:** The `_audit_stats.html` daily throughput chart uses pure CSS flex bars. Reuse this pattern for all chart visualizations.

**When to use:** Any bar/histogram chart in the analytics dashboard.

**Example:**

```html
<!-- Source: [CITED: app/templates/partials/_audit_stats.html lines 43-58] -->
<div class="flex items-end gap-1 h-24">
  {% for day in stats.daily_throughput %}
  <div class="flex-1 flex flex-col items-center justify-end h-full">
    <div class="w-full bg-blue-500 rounded-t"
         style="height: {{ (day.count / max_count * 100) if max_count > 0 else 0 }}%; min-height: 2px;"
         title="{{ day.date }}: {{ day.count }} decisions"></div>
    <span class="text-gray-400 mt-1" style="font-size: 8px;">{{ day.date[5:] }}</span>
  </div>
  {% endfor %}
</div>
```

### Pattern 4: Average Wait Time Calculation

**What:** Average time between review submission (first AuditEntry) and decision (approve/reject AuditEntry). The audit_api.py already implements this pattern with subqueries.

**When to use:** Average review wait time metric.

**Example:**

```python
# Source: [CITED: app/api/v1/audit_api.py lines 213-246]
# Existing pattern uses earliest_subq + decision_subq with AVG extraction
earliest_subq = (
    select(
        AuditEntry.review_id,
        func.min(AuditEntry.created_at).label("first_entry"),
    )
    .group_by(AuditEntry.review_id)
    .subquery()
)
decision_subq = (
    select(
        AuditEntry.review_id,
        func.min(AuditEntry.created_at).label("first_decision"),
    )
    .where(AuditEntry.action.in_(["approve", "reject"]))
    .group_by(AuditEntry.review_id)
    .subquery()
)
avg_time_stmt = select(
    func.avg(
        func.extract("epoch", decision_subq.c.first_decision - earliest_subq.c.first_entry)
        / 60.0
    ).label("avg_minutes")
).join(earliest_subq, earliest_subq.c.review_id == decision_subq.c.review_id)
```

### Pattern 5: AUTO/HUMAN Ratio from ShotCard

**What:** Query `ShotCard.routing_decision` enum to count AUTO vs HUMAN vs AI_AUDIT vs BLOCK.

**When to use:** Routing ratio metric.

**Example:**

```python
# Source: [CITED: app/models/shot_card.py RoutingDecision enum]
from app.models.shot_card import RoutingDecision

routing_result = await session.execute(
    select(
        ShotCard.routing_decision,
        func.count().label("count"),
    )
    .where(
        ShotCard.routing_decision.isnot(None),
        ShotCard.created_at >= start_dt,
        ShotCard.created_at <= end_dt,
    )
    .group_by(ShotCard.routing_decision)
)
```

### Anti-Patterns to Avoid

- **使用 Chart.js / D3 等重量级图表库:** 项目约定零构建步骤（zero-build），所有前端通过 CDN 加载。添加图表库违背 CLAUDE.md 约束，且现有 CSS bar pattern 已满足需求。 [CITED: CLAUDE.md]
- **在 Python 层做聚合:** 大量聚合计算应使用 SQL GROUP BY，而不是 Python 循环。现有 `_audit_stats.html` 的 rejection_reasons 聚合在 Python 中是因为从 JSONB payload 提取，但 source_system/phase 聚合应在 SQL 层完成。
- **混合 V1 和 V2 数据模型不加区分:** V1 Review 用 `source_system` 列 + `metadata_json.phase`；V2 ShotCard 用 `narrative_context.scene/phase` + `routing_decision` 列。Analytics API 需要明确查询哪条路径，或两条路径分别查询后合并。
- **在模板中做数据转换:** 所有聚合、计算、百分比应在 Python/SQL 层完成，模板只负责渲染。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 审核统计聚合 | Python 循环遍历所有 AuditEntry | SQLAlchemy GROUP BY + func.count/sum | SQL 聚合比 Python 循环快 100x+，尤其当数据量增长 |
| 评分分布直方图 | Python 手动 bucket 计数 | SQL CASE WHEN bucket + GROUP BY | 数据库层分桶更高效 |
| 平均等待时间 | Python 遍历每条 review 计算 delta | SQL AVG(epoch extraction) | 单条 SQL 比多条查询 + Python 计算快得多 |
| 日期范围过滤 | 自定义 date string parsing | 复用现有 start_date/end_date Query 参数 + date.fromisoformat | 已有验证模式，无需重写 |
| 批量审核 API | 自定义批量审核逻辑 | 现有 BatchApproveRequest + batch_approve_reviews | API 层已完整实现，包括 207 Multi-Status、audit trail、optimistic locking |

**Key insight:** 本阶段的核心价值是"聚合 + 展示"。SQL 层完成所有聚合计算，Jinja2 模板渲染结果，HTMX 处理交互刷新。批量审核的 API 层已完成，只需补充前端入口。

## Runtime State Inventory

> This is a greenfield analytics dashboard phase. No rename/refactor/migration involved.
> SKIPPED.

## Common Pitfalls

### Pitfall 1: V1 和 V2 数据路径混淆

**What goes wrong:** Analytics 查询混合 Review（V1）和 ShotCard（V2）的数据模型，导致统计口径不一致。
**Why it happens:** V1 Review 有 `source_system` 列和 `metadata_json.phase`（JSONB），V2 ShotCard 有 `routing_decision` 列和 `narrative_context`（JSONB）。两个模型的状态字段名不同（Review: `state`/`disposition`，ShotCard: `audit_status`/`routing_decision`）。
**How to avoid:** 明确每条查询的目标模型。V1 analytics（按 source_system/phase 分组的通过率）走 AuditEntry + Review JOIN；V2 analytics（AUTO/HUMAN 比例、评分分布）走 ShotCard。在 API endpoint 文档中注明数据源。
**Warning signs:** 查询中同时出现 Review 和 ShotCard 的字段但没有 JOIN 条件。

### Pitfall 2: AuditEntry 审计轨迹缺失 average decision time

**What goes wrong:** 现有 `audit_stats_partial` 路由中 `avg_decision_time_minutes` 被硬编码为 `0.0`（第 735 行），因为 web route 中的计算被简化了。而 `audit_api.py` 中的 API 端点有完整的子查询计算。
**Why it happens:** Web 路由简化了计算逻辑以避免复杂子查询。
**How to avoid:** Analytics dashboard 必须使用完整的时间计算子查询（复用 audit_api.py 中的模式），不能硬编码为 0。
**Warning signs:** Dashboard 显示所有等待时间为 0 或 N/A。

### Pitfall 3: JSONB ai_score 为空时查询报错

**What goes wrong:** `ShotCard.narrative_context["ai_score"].astext.cast(Integer)` 在 ai_score 不存在时可能返回 NULL 或报错。
**Why it happens:** 不是所有 ShotCard 都有 ai_score——只有 movie-agent quality-gate phase 才提交评分。
**How to avoid:** 所有 ai_score 相关查询必须加 `WHERE narrative_context["ai_score"].astext IS NOT NULL` 过滤。使用 `func.count()` 统计有效评分数量，避免除零。
**Warning signs:** Score distribution 查询返回 0 条结果或报错。

### Pitfall 4: 批量审核前端缺少加载状态和错误处理

**What goes wrong:** 用户批量审核 50+ 条记录时，页面长时间无反馈。BatchApproveRequest API 虽然已有 per-item 结果，但前端没有展示。
**Why it happens:** 现有 workstation batch 操作（`batch_approve_shot_cards_htmx`）只是简单的 `await session.commit()` 没有 per-item 审计轨迹。
**How to avoid:** Web UI 的批量审核应：(1) 显示加载状态，(2) 展示 per-item 成功/失败结果，(3) 支持 toast 通知成功/跳过数量。
**Warning signs:** 批量操作后用户不知道哪些成功、哪些失败。

### Pitfall 5: Date range 默认值不合理

**What goes wrong:** 默认 date range 太长（30 天）或太短（1 天），导致查询慢或数据不足。
**Why it happens:** Audit cockpit 默认 7 天是合理的，但 analytics dashboard 可能有不同需求。
**How to avoid:** 复用 audit cockpit 的 7 天默认值。添加快捷按钮：Today / 7d / 30d / All time。
**Warning signs:** Analytics 首次加载超过 2 秒。

## Code Examples

### Example 1: Analytics Summary by Source System (V1 path)

```python
# Source: [CITED: app/web/routes.py audit_stats_partial pattern]
# New endpoint: GET /api/v1/analytics/by-source

from sqlalchemy import case, select, func
from app.models.schema import Review, AuditEntry

async def get_analytics_by_source(session, start_dt, end_dt):
    stmt = (
        select(
            Review.source_system,
            func.count().label("total"),
            func.sum(case((AuditEntry.action == "approve", 1), else_=0)).label("approved"),
            func.sum(case((AuditEntry.action == "reject", 1), else_=0)).label("rejected"),
        )
        .join(AuditEntry, AuditEntry.review_id == Review.id)
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
        .group_by(Review.source_system)
        .order_by(Review.source_system)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "source_system": r[0],
            "total": r[1],
            "approved": r[2],
            "rejected": r[3],
            "approval_rate": round(r[2] / r[1], 4) if r[1] > 0 else 0.0,
        }
        for r in rows
    ]
```

### Example 2: Analytics Summary by Phase (V1 path)

```python
# Source: [CITED: app/models/schema.py Review.metadata_json JSONB]
# Extract phase from Review.metadata_json JSONB

async def get_analytics_by_phase(session, start_dt, end_dt):
    stmt = (
        select(
            func.json_extract_path_text(Review.metadata_json, "phase").label("phase"),
            func.count().label("total"),
            func.sum(case((AuditEntry.action == "approve", 1), else_=0)).label("approved"),
            func.sum(case((AuditEntry.action == "reject", 1), else_=0)).label("rejected"),
        )
        .join(AuditEntry, AuditEntry.review_id == Review.id)
        .where(
            AuditEntry.action.in_(["approve", "reject"]),
            AuditEntry.created_at >= start_dt,
            AuditEntry.created_at <= end_dt,
        )
        .group_by("phase")
        .order_by(func.count().desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "phase": r[0] or "unspecified",
            "total": r[1],
            "approved": r[2],
            "rejected": r[3],
            "approval_rate": round(r[2] / r[1], 4) if r[1] > 0 else 0.0,
        }
        for r in result.all()
    ]
```

### Example 3: AUTO/HUMAN Routing Ratio (V2 path)

```python
# Source: [CITED: app/models/shot_card.py RoutingDecision enum]

from app.models.shot_card import ShotCard, RoutingDecision

async def get_routing_ratio(session, start_dt, end_dt):
    stmt = (
        select(
            ShotCard.routing_decision,
            func.count().label("count"),
        )
        .where(
            ShotCard.routing_decision.isnot(None),
            ShotCard.created_at >= start_dt,
            ShotCard.created_at <= end_dt,
        )
        .group_by(ShotCard.routing_decision)
    )
    result = await session.execute(stmt)
    total = 0
    counts = {}
    for r in result.all():
        decision = r[0] if r[0] else "UNKNOWN"
        counts[decision] = r[1]
        total += r[1]

    return {
        "total": total,
        "counts": counts,
        "ratios": {k: round(v / total, 4) for k, v in counts.items()} if total > 0 else {},
    }
```

### Example 4: AI Score Distribution Histogram

```python
# Source: [CITED: app/models/shot_card.py narrative_context JSONB]
# Phase 24 stores ai_score in narrative_context

from sqlalchemy import case, Integer, cast

async def get_score_distribution(session, start_dt, end_dt):
    score_col = ShotCard.narrative_context["ai_score"].astext
    stmt = (
        select(
            case(
                (cast(score_col, Integer) >= 90, "90-100"),
                (cast(score_col, Integer) >= 70, "70-89"),
                (cast(score_col, Integer) >= 50, "50-69"),
                (cast(score_col, Integer) >= 30, "30-49"),
                else_="0-29",
            ).label("bucket"),
            func.count().label("count"),
            func.avg(cast(score_col, Integer)).label("avg_score"),
        )
        .where(
            score_col.isnot(None),
            ShotCard.created_at >= start_dt,
            ShotCard.created_at <= end_dt,
        )
        .group_by("bucket")
        .order_by("bucket")
    )
    result = await session.execute(stmt)
    return [
        {"bucket": r[0], "count": r[1], "avg": round(r[2], 1) if r[2] else None}
        for r in result.all()
    ]
```

### Example 5: Batch Review Web UI Entry Point (HTMX)

```html
<!-- Source: [CITED: app/templates/partials/_batch_toolbar.html pattern] -->
<!-- New: Batch action form for V1 reviews -->

<div x-data="{ selectedIds: [], batchComment: '' }">
  <!-- Review selection checkboxes -->
  <template x-for="review in reviews" :key="review.id">
    <input type="checkbox" :value="review.id"
           @change="$event.target.checked ? selectedIds.push(review.id) : selectedIds = selectedIds.filter(id => id !== review.id)">
  </template>

  <!-- Batch actions bar -->
  <div x-show="selectedIds.length > 0" class="fixed bottom-0 left-0 right-0 bg-gray-800 p-3">
    <span x-text="selectedIds.length + ' reviews selected'"></span>
    <input type="text" x-model="batchComment" placeholder="Comment (optional)">
    <button hx-post="/reviews/batch/approve"
            hx-headers='{"X-CSRF": "token"}'
            hx-vals='js:{review_ids: selectedIds, comment: batchComment}'
            hx-target="#review-list"
            hx-swap="innerHTML"
            class="bg-green-600 text-white px-4 py-2 rounded">
      Batch Approve
    </button>
  </div>
</div>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Audit cockpit flat stats | Grouped analytics by source_system/phase | This phase | 从单一聚合到分组聚合，提供下钻能力 |
| avg_decision_time hardcoded 0.0 | Real avg wait time calculation | This phase | 修复 web route 中的简化计算，复用 audit_api.py 子查询模式 |
| V1 batch API without Web UI | HTMX batch review with per-item feedback | This phase | API 已完整，只需 Web 前端入口 |
| No AI score visibility | Score distribution histogram | Phase 24 stored scores, this phase visualizes | 评分数据已存储在 JSONB，需要聚合展示 |

**Deprecated/outdated:**
- `audit_stats_partial` 中的 `avg_decision_time_minutes = 0.0`（routes.py 第 735 行）：硬编码需要替换为真实计算。
- Audit cockpit 仅限 auditor/admin 角色：Analytics dashboard 应面向所有认证用户。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | V1 Review 的 metadata_json 中 "phase" 字段可通过 `func.json_extract_path_text` 提取 | Code Examples | 如果 metadata 结构不同，需要调整 JSONB path |
| A2 | V2 ShotCard.narrative_context["ai_score"] 存在且为可转 int 的字符串 | Code Examples | 如果 ai_score 不在 narrative_context 顶层或格式不同，查询需调整 |
| A3 | PostgreSQL 的 `func.json_extract_path_text` 可用于 JSONB 字段提取 | Code Examples | 需要 asyncpg 支持，项目已用 PostgreSQL + asyncpg [VERIFIED: app/core/database.py] |
| A4 | BatchApproveRequest 的 Web UI 入口应该复用现有 workstation 的 batch 模式 | Architecture | 如果需要不同的 batch UI 模式，设计需调整 |
| A5 | Analytics dashboard 不需要实时刷新（定时刷新足够） | Architecture | 如果需要实时推送，需要 SSE 集成，增加复杂度 |
| A6 | 审核等待时间的业务定义是"从 review 创建（first AuditEntry）到第一次 approve/reject 决策" | Code Examples | 如果业务定义不同（如从 APPROVING 状态开始计算），需要调整 |

## Open Questions

1. **Analytics dashboard 页面位置**
   - What we know: Audit cockpit 已存在于 `/audit-cockpit`，role-restricted (auditor/admin)。Dashboard 主页 `/` 是 V1 review list。
   - What's unclear: Analytics dashboard 是否应该作为 audit cockpit 的扩展（新 tab），还是独立的 `/analytics` 页面？
   - Recommendation: 独立 `/analytics` 页面，因为：(1) 访问控制不同（所有认证用户 vs auditor/admin），(2) 布局不同（metric cards + charts vs 三栏 cockpit），(3) 关注点不同（运营指标 vs 审计追踪）。

2. **V1 和 V2 数据合并策略**
   - What we know: V1 analytics 走 AuditEntry + Review，V2 analytics 走 ShotCard。两个路径有不同的状态字段名和聚合粒度。
   - What's unclear: 是否需要合并 V1/V2 数据展示在同一视图中？
   - Recommendation: 分开展示。source_system/phase 分组的通过率走 V1 路径（有完整 AuditEntry），AUTO/HUMAN 比例和评分分布走 V2 路径（ShotCard 有 routing_decision）。前端用 tab 或 section 分隔。

3. **批量审核 Web UI 的入口位置**
   - What we know: Workstation 已有 ShotCard batch 操作（`batch_approve_shot_cards_htmx`）。V1 review dashboard（`/`）没有批量操作入口。
   - What's unclear: V1 批量审核 UI 应加在哪里？Review list 页面还是 workstation？
   - Recommendation: 在现有 review list 页面（`/`）中添加复选框和批量操作栏。Workstation 的 batch 操作已覆盖 ShotCard 路径。

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies -- all changes are code/config within existing stack. Database is PostgreSQL + asyncpg, already verified in config.py.)

## Sources

### Primary (HIGH confidence)
- app/web/routes.py (lines 634-753) -- audit_stats_partial query pattern for reuse
- app/api/v1/audit_api.py (lines 158-312) -- complete audit stats aggregation with avg wait time
- app/api/v1/actions.py -- BatchApproveRequest + batch_approve_reviews implementation
- app/models/schema.py -- Review, AuditEntry models with source_system, metadata_json JSONB
- app/models/shot_card.py -- ShotCard model with routing_decision, narrative_context JSONB
- app/models/schemas.py -- BatchApproveRequest, BatchRejectRequest, BatchResponse schemas
- app/templates/partials/_audit_stats.html -- CSS bar chart pattern for reuse
- app/templates/pages/audit_cockpit.html -- Existing three-column cockpit layout
- INTEGRATION.md (lines 67-83) -- Phase 4C.1 + 4C.3 requirements

### Secondary (MEDIUM confidence)
- app/templates/partials/_batch_toolbar.html -- Existing batch toolbar partial
- app/core/audit.py -- AuditLogger with hash chain (for understanding audit trail)
- app/core/state_machine.py -- State transitions (for understanding state model)
- app/core/database.py -- PostgreSQL async engine configuration
- app/policies/movie_agent_phases.yaml -- Routing dispositions by phase
- app/policies/gold_team_risk.yaml -- Routing dispositions by task type

### Tertiary (LOW confidence)
- None -- all findings verified against codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new packages, all verified in requirements.txt and codebase
- Architecture: HIGH - Data sources (AuditEntry, Review, ShotCard) and query patterns well understood from existing code
- Pitfalls: HIGH - Identified from existing codebase (hardcoded avg_time, V1/V2 model differences, JSONB access patterns)
- Batch review: HIGH - API layer fully implemented, only Web UI entry point needed

**Research date:** 2026-05-18
**Valid until:** 2026-06-18 (stable - no external dependencies or fast-moving APIs)
