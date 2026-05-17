# kais-review-platform 集成开发指导

> 来源: kais-aigc-integration 契约层
> 更新: 2026-05-17
> 状态: Phase 0 收尾中

## 当前架构状态

本 repo 已大幅演进，具备 V1 Review API + V2 Shot Card 双层架构：

**V1 Review API**（通用审核）:
- `POST /api/v1/reviews/` — 提交审核
- `POST /api/v1/reviews/{id}/approve` — 批准
- `POST /api/v1/reviews/{id}/reject` — 拒绝
- `ApproveRequest` 仅支持 `comment`（不支持 result/selected/scores）
- 回调 payload 不携带审核结果详情

**V2 Shot Card API**（短片专用）:
- `POST /api/v1/shot-cards/` — 创建 Shot Card（含 candidates、visual_bundle）
- `POST /api/v1/shot-cards/{id}/approve` — 批准
- `Candidate` 模型原生支持多候选
- `MobileShotCardBundle` 已展开 candidates 字段

**其他已实现能力**:
- RBAC 多角色认证（Role enum + JWT claims）
- Merkle 树审计 + 双写 + Git anchoring
- A/B 测试 + Shadow Score
- 批量审核（`BatchApproveRequest`）
- 策略引擎 V1 + V2
- 审计驾驶舱 + 移动端 dashboard

## 集成决策：movie-agent 应使用哪个 API?

### 方案 A：继续用 V1 Review API + 扩展 ApproveRequest

在 `ApproveRequest` 上加 `result` 字段，回调 payload 带上结果。

**优点**: 改动小，向后兼容，movie-agent 已有 `ReviewPlatformClient`
**缺点**: 多候选数据塞在 metadata 里，不如 V2 结构化

### 方案 B：迁移到 V2 Shot Card API

movie-agent 直接用 `shot-cards` 端点，原生支持 candidates。

**优点**: 数据结构化，原生多候选，移动端 UI 已适配
**缺点**: movie-agent 需要重写客户端，Shot Card 的 schema（narrative_context、visual_bundle）与 movie-agent 的 phase 产出需要对齐

### 建议选择

**短期内用方案 A**（V1 + 扩展），原因是 movie-agent 的 `ReviewPlatformClient` 已写好。后续按需迁移方案 B。

---

## 本 Repo 的集成任务

### Task 1 [P0] V1 ApproveRequest 扩展 result 字段

**问题**: movie-agent 审核完成后需要拿回 `selected`/`scores`/`feedback`，但当前 V1 approve 只存 `comment`。

**修改文件**: `app/models/schemas.py`

```python
# 在 ApproveRequest 之后新增
class ReviewResult(BaseModel):
    selected: list[int] | None = None
    scores: list[dict] | None = None     # [{"id": 1, "score": 9, "comment": "..."}]
    feedback: str | None = None

class ApproveRequest(BaseModel):
    """V1 legacy approve request — extended with result support."""
    comment: str | None = None
    result: ReviewResult | None = None   # 新增
```

**修改文件**: `app/api/v1/actions.py`

在 `approve_review()` 中把 result 存入 `metadata_json`:

```python
if request.result:
    metadata = review.metadata_json or {}
    metadata["review_result"] = request.result.model_dump()
    review.metadata_json = metadata
```

**修改文件**: `app/workers/tasks.py` — 回调 payload 带上 result

```python
payload["result"] = review.metadata_json.get("review_result") if review.metadata_json else None
```

**契约文件**: `contracts/callback-schemas/review-callback.json`

---

### Task 2 [P1] 健康检查增强

**位置**: `app/api/v1/` 或 `app/main.py`

```python
@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "version": "1.2.0",
        "redis": bool(redis.ping()),
        "db": True,  # 简单查询
        "active_sse": event_mgr.connection_count,
    }
```

---

### Task 3 [P1] movie-agent 各 phase 策略文件

**位置**: `app/policies/movie_agent_phases.yaml`

检查是否已有此文件。如没有，新建:

```yaml
name: movie_agent_phases
version: "1.0"
rules:
  - name: art_direction_human
    priority: 1
    conditions:
      operator: AND
      checks:
        - field: source_system
          operator: equals
          value: kais-movie-agent
        - field: metadata.phase
          operator: equals
          value: art-direction
    disposition: HUMAN

  - name: character_human
    priority: 2
    conditions:
      operator: AND
      checks:
        - field: source_system
          operator: equals
          value: kais-movie-agent
        - field: metadata.phase
          operator: equals
          value: character
    disposition: HUMAN

  - name: voice_human
    priority: 3
    conditions:
      operator: AND
      checks:
        - field: source_system
          operator: equals
          value: kais-movie-agent
        - field: metadata.phase
          operator: equals
          value: voice
    disposition: HUMAN

  - name: quality_gate_auto
    priority: 10
    conditions:
      operator: AND
      checks:
        - field: source_system
          operator: equals
          value: kais-movie-agent
        - field: metadata.phase
          operator: equals
          value: quality-gate
    disposition: AUTO
```

---

### Task 4 [P2] 多候选审核 UI（V1 Review Web）

当 review 的 metadata 包含 candidates 时，审核详情页渲染多候选选择 UI。

**位置**: `app/web/routes.py` — `review_detail_partial()`

检测 `metadata.candidates` 存在时渲染并排图片 + 评分 + 选择按钮。

---

## 环境变量

```bash
# 集成相关（给 movie-agent 和 gold-team 分配的 key）
RP_API_KEY_MOVIE_AGENT=rp-movie-agent-secret-key
RP_API_KEY_GOLD_TEAM=rp-gold-team-secret-key
```

## 任务优先级

| # | 任务 | 优先级 | 预估 |
|---|------|--------|------|
| 1 | V1 ApproveRequest 扩展 result + 回调 payload | P0 | 1-2h |
| 2 | 健康检查增强 | P1 | 30min |
| 3 | movie-agent 策略文件 | P1 | 30min |
| 4 | 多候选审核 UI | P2 | 2-3h |

**先做 Task 1** — 这是 movie-agent 审核结果回传的阻塞项。
