"""G15 ops — per-shot waive/requeue 服务端落点(v3.2 Phase 67 / WBX-01)。

由来(2026-08-25 review F09/F14/F27):kap g15Bridge POST 的 /api/v1/g15/ops
此前全网 404——画布豁免操作恒「未送达」,只能入 canvas_writeback_queue 重放,
UI 诚实降级。本端点补齐服务端,并把**逐镜头豁免子集**合并进 APPROVING
review 的 ``metadata.review_result``(union 幂等)——kmc 30s poller 读
``review_result.waived_shot_ids`` 消费子集语义(runner_hooks 67-03 注入),
终结「approve = 全量一刀切」的错放行(F15)。

设计要点:
  - review **不在本端点转终态**:豁免子集后仍 APPROVING;operator 的
    approve(web/telegram)才是终态动作,approve 端点保留已积累的
    waived_shot_ids(actions.py 67-02 carry-forward 同步修)。
  - 候选匹配 fail-closed:type == gate + source=kais-movie-agent +
    content_ref episode 段 ∈ episodeRefs(kap 侧画布探针解析,WR-01 同源);
    0 命中 404、≥2 命中 409(歧义不动手,宁漏不错批)。
  - requeue:同样合并 requeue_shot_ids 留痕;kmc 重渲消费端 v3.2 Phase 69
    落地(当前仅记录,不触发动作)。
  - 409 幂等语义与 approve 家族一致:kap 桥把 409 视为「已在别处处理」。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_audit
from app.core.database import get_db
from app.core.auth import get_current_client
from app.models.schema import Review
from app.models.schemas import ApiResponse, G15OpsRequest, G15OpsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/g15", tags=["g15-ops"])

_MAX_SHOT_IDS = 200
_SHOT_KEY_BY_ACTION = {"waive": "waived_shot_ids", "requeue": "requeue_shot_ids"}


@router.post("/ops", response_model=ApiResponse[G15OpsResponse])
async def g15_ops(
    request: G15OpsRequest,
    db: AsyncSession = Depends(get_db),
    client: str = Depends(get_current_client),
) -> ApiResponse[G15OpsResponse]:
    """Per-shot waive/requeue on the open gate review (subset semantics)."""
    actor = f"client:{client}"
    refs = set(request.episode_refs or []) | {request.episodeId}

    result = await db.execute(
        select(Review).where(
            Review.state == "APPROVING",
            Review.type == request.gate,
            Review.source_system == "kais-movie-agent",
        )
    )
    candidates = [r for r in result.scalars().all() if _episode_of(r.content_ref) in refs]

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No open {request.gate} review for episode {request.episodeId} "
            f"(refs={sorted(refs)}) — the gate may not be awaiting review",
        )
    if len(candidates) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ambiguous: {len(candidates)} open {request.gate} reviews match — refusing to act",
        )

    review = candidates[0]
    shot_key = _SHOT_KEY_BY_ACTION[request.action]
    metadata = dict(review.metadata_json or {})
    prev_result = dict(metadata.get("review_result") or {})
    merged_ids = sorted(
        set(prev_result.get(shot_key) or []) | set(request.shotIds)
    )
    metadata["review_result"] = {**prev_result, shot_key: merged_ids}

    stmt = (
        update(Review)
        .where(Review.id == review.id, Review.version == review.version)
        .values(metadata_json=metadata, version=review.version + 1)
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="State conflict: review was modified concurrently — retry is safe (union idempotent)",
        )
    await db.commit()
    await append_audit(
        db,
        review_id=review.id,
        action=f"g15_{request.action}",
        actor=actor,
        from_state=review.state,
        to_state=review.state,
        payload={
            "gate": request.gate,
            "shot_ids": request.shotIds,
            "comment": request.comment,
            "merged_count": len(merged_ids),
        },
    )
    await db.commit()

    logger.info(
        "g15_ops",
        action=request.action,
        gate=request.gate,
        review_id=review.id,
        shots=len(request.shotIds),
        merged=len(merged_ids),
    )
    return ApiResponse(
        data=G15OpsResponse(
            delivered=True,
            review_id=review.id,
            gate=request.gate,
            action=request.action,
            shot_ids=merged_ids,
            applied_at=datetime.now(timezone.utc).isoformat(),
        ),
        meta={"request_id": f"g15-{review.id}-{request.action}"},
    )


def _episode_of(content_ref: str) -> str:
    """content_ref 'ep-xxx/p11b_final_render' → 'ep-xxx' (WR-01 episode 段)."""
    return content_ref.rsplit("/", 1)[0] if "/" in content_ref else content_ref
