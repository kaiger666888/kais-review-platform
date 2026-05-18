# Phase 24: External Scoring Integration - Research

**Researched:** 2026-05-18
**Domain:** External AI score storage + read-only display in review UI
**Confidence:** HIGH

## Summary

Phase 24 接入 movie-agent 的 quality-gate AI 评分到审核平台。核心任务分两部分：(1) V1 Review submission API 接收 `metadata.ai_score` / `ai_score_dimensions` / `ai_score_source` 并存储到 Review 的 JSONB `metadata_json` 字段；(2) V2 Shot Card 同样需要存储外部评分并在桌面和移动端 UI 上以只读方式展示各维度分数（visual_quality, audio_quality, consistency）。

关键发现：V1 的 `metadata_json` 已经是 JSONB 字段，可以无 schema 变更地存储任意嵌套数据（包括 `ai_score` 字段）。V2 ShotCard 没有专门的评分列，但 `narrative_context` JSONB 已是灵活容器 -- 可在其中新增 `ai_score` / `ai_score_dimensions` / `ai_score_source` 子字段，或新增独立 JSONB 列。Phase 23 的模板系统已有 `show_scores: true` 配置项，movie-agent 的 quality-gate 模板已设置 `show_scores: true`，且 `_template_candidate_grid.html` 已有候选分数 badge 渲染逻辑。本阶段需要扩展的是 ShotCard 级别的整体 AI 评分（非候选级别），在决策面板和移动卡片中新增展示。

**Primary recommendation:** 利用现有 JSONB 字段存储评分（V1: metadata_json, V2: narrative_context 或新增 ai_scores JSONB 列），通过 Jinja2 模板扩展 + Alpine.js 条件渲染展示评分维度。无需数据库 migration（JSONB 自适应）或新增依赖包。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| AI score 接收与存储 | API / Backend | -- | FastAPI endpoint 接收 metadata，写入 JSONB 字段 |
| AI score API 返回 | API / Backend | -- | 响应模型中包含评分数据，前端被动消费 |
| 桌面评分展示 | Frontend Server (SSR) | Browser / Client | Jinja2 服务端渲染评分面板，HTMX 局部刷新 |
| 移动评分展示 | Browser / Client | API / Backend | Alpine.js 客户端条件渲染，依赖 mobile API 返回的 template_config |
| 评分数据源 | External (movie-agent) | -- | 外部系统通过 V1 Review API 提交评分数据 |

## Standard Stack

### Core

No new packages required. Phase uses existing stack:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136 | API endpoint for score reception | Already in requirements.txt, handles JSONB natively [VERIFIED: requirements.txt] |
| Pydantic | 2.13.3 | Score schema validation | Optional typed model for ai_score_dimensions [VERIFIED: requirements.txt] |
| SQLAlchemy | 2.0.49 | JSONB column access | JSONB stores nested score data without migration [VERIFIED: requirements.txt] |
| Jinja2 (built-in) | -- | Desktop score panel rendering | Server-side partial rendering with existing template system [VERIFIED: codebase] |
| Alpine.js | 3.15.12 | Mobile conditional score display | Client-side reactive rendering from API data [VERIFIED: CLAUDE.md] |

### Supporting

N/A -- no additional supporting libraries needed.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| JSONB flexible storage | Dedicated score columns (FLOAT) | Dedicated columns add Alembic migration, rigid schema. JSONB allows arbitrary dimensions without DDL. Preferred for V1 where metadata is already JSONB. |
| narrative_context JSONB for scores | New ai_scores JSONB column | New column is cleaner separation but requires migration + aggregation pipeline update. narrative_context already carries pipeline metadata. Recommend: use narrative_context for V2 ShotCard with namespaced keys (`ai_score`, `ai_score_dimensions`, `ai_score_source`). |

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
movie-agent                   review-platform (FastAPI)
    |                              |
    | POST /api/v1/reviews/        |
    | {metadata: {                 |
    |   ai_score: 72,              |
    |   ai_score_dimensions: {...},|
    |   ai_score_source: "..."     |
    | }}                           |
    |----------------------------->|
    |                              |----> Store in Review.metadata_json (JSONB)
    |                              |----> (V2) Store in ShotCard.narrative_context (JSONB)
    |                              |
    |  GET /api/v1/reviews/{id}    |
    |<-----------------------------|
    |  {metadata: {ai_score: ...}} |
    |                              |
    |  GET /api/v1/shot-cards/{id} |
    |<-----------------------------|
    |  {narrative_context: {...,   |
    |    ai_score: ...}}           |
    |                              |
    |        Desktop UI (SSR)      |
    |  Jinja2 renders score panel  |
    |  if template.show_scores     |
    |                              |
    |        Mobile UI (Alpine.js) |
    |  Conditional render from     |
    |  template_config.show_scores |
```

### Recommended Project Structure

```
app/
├── models/
│   └── schemas.py          # Add AIScoreDimensions Pydantic model (optional)
├── api/v1/
│   ├── reviews.py          # V1: ai_score already flows through metadata
│   ├── shot_cards.py       # V2: ensure narrative_context ai_score in response
│   └── mobile.py           # Extract ai_score fields into MobileShotCardBundle
├── templates/
│   └── partials/
│       ├── _decision_panel.html        # Add score dimensions section
│       ├── _template_candidate_grid.html # Add overall AI score panel
│       └── _mobile_card.html           # Add score badges in detail panel
```

### Pattern 1: JSONB Nested Score Storage

**What:** Store external AI scores as nested keys within existing JSONB columns, avoiding schema migration.

**When to use:** When the scoring structure is externally defined and may evolve (new dimensions).

**Example:**

```python
# V1: Already works via ReviewCreateRequest.metadata (dict)
# movie-agent POST /api/v1/reviews/
{
  "metadata": {
    "phase": "quality-gate",
    "ai_score": 72,
    "ai_score_dimensions": {
      "visual_quality": 80,
      "audio_quality": 65,
      "consistency": 70
    },
    "ai_score_source": "movie-agent"
  }
}

# V2: narrative_context gains score keys (via aggregator or direct update)
shot_card.narrative_context = {
  "scene": "S001",
  "shot_number": 1,
  "emotion_curve": "neutral -> tense",
  "ai_score": 72,
  "ai_score_dimensions": {
    "visual_quality": 80,
    "audio_quality": 65,
    "consistency": 70
  },
  "ai_score_source": "movie-agent"
}
```

Source: [INTEGRATION.md 4B.2] [CITED: INTEGRATION.md]

### Pattern 2: Template-Conditional Score Display

**What:** Use Phase 23's `TemplateConfig.show_scores` flag to gate score rendering.

**When to use:** Only templates with `show_scores: true` render AI score panels.

**Example (Jinja2 desktop):**

```html
{% if template and template.show_scores %}
{% set nc = shot.narrative_context or {} %}
{% if nc.get('ai_score') is not none %}
<div class="space-y-2">
  <h3 class="text-xs font-semibold uppercase text-gray-500">AI Score</h3>
  <div class="flex items-center gap-2">
    <span class="text-lg font-bold text-blue-400">{{ nc.ai_score }}</span>
    <span class="text-xs text-gray-500">/ 100</span>
  </div>
  {% if nc.get('ai_score_dimensions') %}
  <div class="space-y-1">
    {% for dim, val in nc.ai_score_dimensions.items() %}
    <div class="flex items-center justify-between">
      <span class="text-xs text-gray-400">{{ dim }}</span>
      <span class="text-xs font-mono {% if val >= 70 %}text-green-400{% elif val >= 50 %}text-yellow-400{% else %}text-red-400{% endif %}">{{ val }}</span>
    </div>
    {% endfor %}
  </div>
  {% endif %}
  {% if nc.get('ai_score_source') %}
  <div class="text-xs text-gray-500">Source: {{ nc.ai_score_source }}</div>
  {% endif %}
</div>
{% endif %}
{% endif %}
```

Source: [CITED: app/templates/config/movie-agent.yaml quality-gate show_scores: true]

### Pattern 3: Mobile Score Badge (Alpine.js)

**What:** Extract ai_score into MobileShotCardBundle, render conditionally via template_config.

**Example (Alpine.js in _mobile_card.html):**

```html
<!-- AI Score badge (shown when template_config.show_scores is true) -->
<template x-if="cards[currentIndex].template_config && cards[currentIndex].template_config.show_scores && cards[currentIndex].ai_score != null">
  <div class="flex items-center gap-1">
    <span class="text-xs text-gray-500">AI:</span>
    <span class="text-xs font-mono font-bold"
          :class="{
            'text-green-400': cards[currentIndex].ai_score >= 70,
            'text-yellow-400': cards[currentIndex].ai_score >= 50 && cards[currentIndex].ai_score < 70,
            'text-red-400': cards[currentIndex].ai_score < 50
          }"
          x-text="cards[currentIndex].ai_score">
    </span>
  </div>
</template>
```

Source: [CITED: app/templates/partials/_mobile_card.html existing pattern]

### Anti-Patterns to Avoid

- **在 review-platform 计算 AI 评分**: INTEGRATION.md 明确声明 review-platform 是纯策略治理平台，不引入 LLM。所有评分由 movie-agent 本地计算后提交。本阶段只做存储和展示。 [CITED: INTEGRATION.md]
- **为评分创建新的数据库表**: 评分数据是 ShotCard/Review 的附加属性，不是独立实体。应使用 JSONB 嵌套存储，而非新建 scores 表。
- **硬编码评分维度名称**: `ai_score_dimensions` 的 key（visual_quality, audio_quality, consistency）由 movie-agent 定义，review-platform 应动态遍历 `dict.items()` 而非硬编码字段名。
- **修改 ShotCard Pydantic schema 强制要求评分**: 评分是可选字段（不是所有 ShotCard 都有 AI 评分）。Schema 中应全部为 `| None = None`。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Score validation | Custom dict validator | Pydantic Optional[dict] | ai_score_dimensions 格式由外部系统定义，review-platform 不应限制其 schema |
| Score color coding | CSS class computation in Python | Jinja2 template conditionals | Color thresholds (green/yellow/red) 属于展示逻辑，留在模板层 |
| Score aggregation | Score averaging/weighting | N/A (不计算) | review-platform 只展示，不计算 |

**Key insight:** 这个阶段的核心约束是"存储 + 展示，不计算"。代码变更集中在 Pydantic model 字段扩展 + Jinja2 模板渲染 + Alpine.js 条件展示。

## Common Pitfalls

### Pitfall 1: V1 和 V2 数据模型不一致

**What goes wrong:** V1 Review 用 `metadata_json` 存评分，V2 ShotCard 用 `narrative_context`。如果评分字段 key 不统一，前端渲染需要两套逻辑。
**Why it happens:** V1 和 V2 是不同的数据路径（V1: Review model, V2: ShotCard model）。
**How to avoid:** 统一评分 key 名称：`ai_score`（number）、`ai_score_dimensions`（dict）、`ai_score_source`（string）。V1 通过 metadata 传入，V2 通过 narrative_context 或聚合器注入，但 key 名保持一致。
**Warning signs:** 模板代码中出现 `metadata.ai_score` 和 `narrative_context.ai_score` 两套访问路径。

### Pitfall 2: narrative_context 污染

**What goes wrong:** 把评分数据塞进 narrative_context 让语义边界模糊 -- narrative_context 应该是叙事信息（scene, shot_number, emotion_curve），不是评分。
**Why it happens:** JSONB 字段"什么都能塞"的便利性。
**How to avoid:** 方案 A：使用 namespaced key（`ai_score`, `ai_score_dimensions` 明确前缀区分）；方案 B：新增 `ai_scores` JSONB 列（更干净但需要 migration）。推荐方案 A，因为当前阶段优先无 migration，且 narrative_context 已经包含 `phase`/`pipeline_phase` 等非叙事元数据。
**Warning signs:** narrative_context 中的非叙事字段超过 5 个。

### Pitfall 3: 评分展示缺少空值保护

**What goes wrong:** 模板尝试渲染 `ai_score_dimensions.visual_quality` 但 ShotCard 没有评分数据，导致 Jinja2 报错或 Alpine.js 显示 undefined。
**Why it happens:** 评分是可选的，只有 movie-agent quality-gate phase 才提交。
**How to avoid:** 所有评分展示代码必须从外到内做空值检查：`{% if nc.get('ai_score') is not none %}` / `x-if="... && cards[i].ai_score != null"`。
**Warning signs:** 模板中出现 `{{ nc.ai_score }}` 而不是 `{{ nc.get('ai_score') }}`。

### Pitfall 4: MobileShotCardBundle 缺少评分字段

**What goes wrong:** 后端 `_shot_card_to_bundle()` 不提取评分字段到 MobileShotCardBundle，前端拿不到数据。
**Why it happens:** MobileShotCardBundle 是手动展平的 Pydantic model，新增 JSONB 字段不会自动出现在响应中。
**How to avoid:** 在 MobileShotCardBundle 中添加 `ai_score: int | None = None`、`ai_score_dimensions: dict | None = None`、`ai_score_source: str | None = None` 字段，在 `_shot_card_to_bundle()` 中提取。
**Warning signs:** 移动端 API 响应中缺少 ai_score 字段。

## Code Examples

### Example 1: V1 Review API - 评分数据流（已实现）

V1 Review submission API 已支持 metadata 中的 ai_score 字段，因为 `metadata_json` 是自由格式 JSONB：

```python
# app/api/v1/reviews.py line 101-104
review = Review(
    type=request.type,
    content_ref=request.content_ref,
    metadata_json=request.metadata,  # <-- ai_score flows through here
    ...
)
```

Source: [CITED: app/api/v1/reviews.py]

### Example 2: MobileShotCardBundle 扩展（需要实现）

```python
# app/models/schemas.py - extend MobileShotCardBundle
class MobileShotCardBundle(BaseModel):
    # ... existing fields ...
    ai_score: int | None = None
    ai_score_dimensions: dict | None = None
    ai_score_source: str | None = None
```

Source: [CITED: app/models/schemas.py MobileShotCardBundle]

### Example 3: _shot_card_to_bundle 扩展（需要实现）

```python
# app/api/v1/mobile.py - extract scores from narrative_context
nc = shot_card.narrative_context or {}
ai_score = nc.get("ai_score")
ai_score_dimensions = nc.get("ai_score_dimensions")
ai_score_source = nc.get("ai_score_source")

return MobileShotCardBundle(
    # ... existing fields ...
    ai_score=ai_score,
    ai_score_dimensions=ai_score_dimensions,
    ai_score_source=ai_score_source,
)
```

Source: [CITED: app/api/v1/mobile.py _shot_card_to_bundle]

### Example 4: V2 ShotCard 创建路径（聚合器需要更新）

movie-agent 的评分需通过聚合器或 node-completed 事件注入 narrative_context：

```python
# Option A: aggregator fills ai_score from event data
narrative_context = event.get("narrative_context", {})
# If event carries ai_score fields, they flow into narrative_context automatically
shot_card = ShotCard(
    shot_id=shot_id,
    project_id=project_id,
    narrative_context=narrative_context,  # ai_score keys included if present
    ...
)
```

Source: [CITED: app/services/aggregator.py _ensure_shot_card]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 无评分展示 | Phase 23 模板系统预留 show_scores | Phase 23 (2026-05-18) | show_scores flag 已就位，只需填充数据 |
| Candidate-level score badge | ShotCard-level AI score panel | This phase | 从候选粒度扩展到整卡粒度的评分展示 |

**Deprecated/outdated:**
- 无 -- 这是新功能，不替换现有逻辑。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | movie-agent 通过 V1 Review API 的 `metadata` 字段提交 ai_score（0-100 整数） | Architecture | 如果 movie-agent 改用 V2 ShotCard API 或评分范围不同，需调整 |
| A2 | V2 ShotCard 的评分数据存储在 `narrative_context` JSONB 中（而非新增列） | Architecture | 如果后续需要索引/查询评分，可能需要独立列 + migration |
| A3 | 评分维度名称（visual_quality, audio_quality, consistency）是 movie-agent 定义的固定集合 | Architecture | 如果维度名称变化，模板动态遍历 dict 可自适应 |
| A4 | 评分数值范围是 0-100 整数 | Code Examples | 如果是 0-1 浮点数，需要调整显示逻辑（x100 转换） |
| A5 | V2 路径中 movie-agent 评分通过 node-completed 事件 narrative_context 传入 | Architecture | 如果 V2 路径不经过聚合器，需要额外的 API endpoint 接收评分 |

## Open Questions

1. **V2 ShotCard 评分注入路径**
   - What we know: V1 Review API 已支持 metadata.ai_score。V2 ShotCard 通过 aggregator 创建，narrative_context 来自 event 数据。
   - What's unclear: movie-agent 是否也会通过 node-completed event 提交评分到 V2 路径，还是只走 V1 Review API？
   - Recommendation: 假设 V1 Review API 是主要入口（INTEGRATION.md 明确展示此路径）。V2 路径通过 narrative_context 传递评分。两个路径都实现。

2. **评分数值范围**
   - What we know: INTEGRATION.md 示例显示 `ai_score: 72`（整数）。
   - What's unclear: 范围是 0-100 还是 0-1？示例暗示 0-100。
   - Recommendation: 按 0-100 整数实现，模板中直接显示数值 + "/100" 后缀。

## Environment Availability

Step 2.6: SKIPPED (no new external dependencies -- all changes are code/config within existing stack)

## Sources

### Primary (HIGH confidence)
- INTEGRATION.md (lines 39-63) - 4B.2 quality-gate 外部评分接收的数据格式
- app/models/schema.py - Review model metadata_json JSONB 字段
- app/models/shot_card.py - ShotCard model narrative_context JSONB 字段
- app/models/schemas.py - MobileShotCardBundle, ReviewCreateRequest, ShotCardResponse
- app/api/v1/reviews.py - V1 Review submission endpoint
- app/api/v1/mobile.py - Mobile bundle with template_config
- app/core/template_registry.py - TemplateConfig.show_scores flag
- app/templates/config/movie-agent.yaml - quality-gate show_scores: true

### Secondary (MEDIUM confidence)
- app/templates/partials/_decision_panel.html - Desktop decision panel structure
- app/templates/partials/_template_candidate_grid.html - Candidate score badge pattern
- app/templates/partials/_mobile_card.html - Mobile card Alpine.js patterns

### Tertiary (LOW confidence)
- None -- all findings verified against codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new packages, all verified in requirements.txt and codebase
- Architecture: HIGH - Data flow path clear from INTEGRATION.md + codebase analysis
- Pitfalls: HIGH - Identified from existing codebase patterns and template system constraints

**Research date:** 2026-05-18
**Valid until:** 2026-06-18 (stable - no external dependencies or fast-moving APIs)
