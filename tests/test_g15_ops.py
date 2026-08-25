"""v3.2 Phase 67 (WBX-01/WBX-04) — g15 ops 端点 + 决策持久化补洞。

F09/F14/F27:kap g15Bridge 的 /api/v1/g15/ops 此前全网 404,豁免恒未送达;
F15:waived_shot_ids 无生产者,p10c/p11c approve=全量一刀切;
F16:web UI/batch 六条路径绕过 decision 持久化,kmc poller 三方读法不一致。

契约:
  1. POST /api/v1/g15/ops {action: waive} — APPROVING review 的
     review_result.waived_shot_ids 合并(union 幂等),review 不转终态;
  2. 0 命中 404 / ≥2 命中 409 / 并发版本冲突 409(重试安全);
  3. episode_refs 匹配 content_ref episode 段(kap 画布探针同源);
  4. approve(单条/批量/web)保留已积累的 waived_shot_ids(carry-forward);
  5. batch approve/reject 与 web htmx 路径落 review_result.decision。
"""

import pytest
import pytest_asyncio

from app.core.state_machine import transition_state
from app.models.schema import Review
from app.models.schemas import ReviewState


async def _mk_approving(db_session, *, type_="p11c-gate",
                        content_ref="ep-zhongkui-ep01/p11c_video_qc",
                        metadata=None):
    r = Review(
        type=type_,
        content_ref=content_ref,
        source_system="kais-movie-agent",
        priority="normal",
        risk_score=0.5,
        state=ReviewState.PENDING.value,
        version=1,
        metadata_json=metadata,
    )
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    r = await transition_state(
        db_session, r.id, ReviewState.PENDING, ReviewState.POLICY_EVAL,
        r.version, actor="system", action="policy_eval_start",
    )
    r = await transition_state(
        db_session, r.id, ReviewState.POLICY_EVAL, ReviewState.APPROVING,
        r.version, actor="system", action="route_human",
        payload={"disposition": "HUMAN"},
    )
    return r


class TestG15OpsEndpoint:
    """WBX-01: per-shot waive/requeue 服务端。"""

    @pytest_asyncio.fixture
    async def http(self, db_session):
        from httpx import ASGITransport, AsyncClient
        from app.core.config import Settings

        _orig = Settings.model_config.get("env_file")
        Settings.model_config["env_file"] = None
        from app.main import app
        from app.core.database import get_db
        from app.core.dependencies import get_redis

        class _RedisStub:
            async def get(self, *a, **k):
                return None

            async def set(self, *a, **k):
                return None

            async def delete(self, *a, **k):
                return None

        async def _db():
            yield db_session

        async def _redis():
            return _RedisStub()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_redis] = _redis
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, db_session
        app.dependency_overrides.clear()
        Settings.model_config["env_file"] = _orig

    @pytest.mark.asyncio
    async def test_waive_subset_merges_union_idempotent(self, http):
        c, db = http
        r = await _mk_approving(db)
        body = {
            "projectId": 7, "episodeId": "ep1", "action": "waive",
            "shotIds": ["S01", "S03"], "gate": "p11c-gate",
            "comment": "豁免两条",
            "episodeRefs": ["ep-zhongkui-ep01", "ep1"],
        }
        resp = await c.post("/api/v1/g15/ops", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["delivered"] is True
        assert data["shot_ids"] == ["S01", "S03"]

        # 幂等 union:第二波豁免合并,不覆盖
        resp2 = await c.post("/api/v1/g15/ops", json={**body, "shotIds": ["S03", "S07"]})
        assert resp2.status_code == 200
        assert resp2.json()["data"]["shot_ids"] == ["S01", "S03", "S07"]

        # review 仍 APPROVING(豁免子集不是终态动作)
        await db.refresh(r)
        assert r.state == ReviewState.APPROVING.value
        assert r.metadata_json["review_result"]["waived_shot_ids"] == [
            "S01", "S03", "S07",
        ]

    @pytest.mark.asyncio
    async def test_requeue_records_subset_no_state_change(self, http):
        c, db = http
        r = await _mk_approving(db)
        resp = await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep-zhongkui-ep01", "action": "requeue",
            "shotIds": ["S02"], "gate": "p11c-gate",
        })
        assert resp.status_code == 200
        await db.refresh(r)
        assert r.state == ReviewState.APPROVING.value
        assert r.metadata_json["review_result"]["requeue_shot_ids"] == ["S02"]

    @pytest.mark.asyncio
    async def test_no_open_review_404(self, http):
        c, _ = http
        resp = await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep-none", "action": "waive",
            "shotIds": ["S01"], "gate": "p11c-gate",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_ambiguous_two_open_reviews_409(self, http):
        c, db = http
        await _mk_approving(db)
        await _mk_approving(db, metadata=None)
        resp = await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep-zhongkui-ep01", "action": "waive",
            "shotIds": ["S01"], "gate": "p11c-gate",
        })
        assert resp.status_code == 409
        assert "Ambiguous" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_gate_mismatch_404(self, http):
        """开着的门是 p11c-gate,请求打 p10c-gate → 404(不误伤他门)。"""
        c, db = http
        await _mk_approving(db)  # p11c-gate open
        resp = await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep-zhongkui-ep01", "action": "waive",
            "shotIds": ["wav1"], "gate": "p10c-gate",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_validation_shot_ids_bounds(self, http):
        c, _ = http
        resp = await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep1", "action": "waive",
            "shotIds": [], "gate": "p11c-gate",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_audit_entry_written(self, http):
        c, db = http
        r = await _mk_approving(db)
        await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep-zhongkui-ep01", "action": "waive",
            "shotIds": ["S01"], "gate": "p11c-gate",
        })
        from sqlalchemy import select
        from app.models.schema import AuditEntry
        rows = (await db.execute(
            select(AuditEntry).where(
                AuditEntry.review_id == r.id,
                AuditEntry.action == "g15_waive",
            )
        )).scalars().all()
        assert len(rows) == 1


class TestApproveCarryForward:
    """WBX-02 前置:approve 不再冲掉已积累的豁免子集。"""

    @pytest_asyncio.fixture
    async def http(self, db_session):
        from httpx import ASGITransport, AsyncClient
        from app.core.config import Settings

        _orig = Settings.model_config.get("env_file")
        Settings.model_config["env_file"] = None
        from app.main import app
        from app.core.database import get_db
        from app.core.dependencies import get_redis

        class _RedisStub:
            async def get(self, *a, **k):
                return None

            async def set(self, *a, **k):
                return None

            async def delete(self, *a, **k):
                return None

        async def _db():
            yield db_session

        async def _redis():
            return _RedisStub()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_redis] = _redis
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, db_session
        app.dependency_overrides.clear()
        Settings.model_config["env_file"] = _orig

    @pytest.mark.asyncio
    async def test_single_approve_preserves_waived_shot_ids(self, http):
        c, db = http
        r = await _mk_approving(db)
        # 预积累豁免子集(g15/ops 已发生)
        await c.post("/api/v1/g15/ops", json={
            "projectId": 7, "episodeId": "ep-zhongkui-ep01", "action": "waive",
            "shotIds": ["S01", "S02"], "gate": "p11c-gate",
        })
        # operator approve(终态)
        resp = await c.post(
            f"/api/v1/reviews/{r.id}/approve", json={"comment": "ok"},
        )
        assert resp.status_code == 200, resp.text
        await db.refresh(r)
        rr = r.metadata_json["review_result"]
        assert rr["decision"] == "approve"
        assert rr["waived_shot_ids"] == ["S01", "S02"], "approve 不得冲掉豁免子集"

    @pytest.mark.asyncio
    async def test_batch_approve_writes_decision(self, http):
        c, db = http
        r1 = await _mk_approving(db)
        r2 = await _mk_approving(db)
        resp = await c.post("/api/v1/reviews/batch/approve", json={
            "review_ids": [r1.id, r2.id], "comment": "batch",
        })
        assert resp.status_code == 207
        body = resp.json()["data"]
        assert body["success_count"] == 2
        for r in (r1, r2):
            await db.refresh(r)
            assert r.metadata_json["review_result"]["decision"] == "approve"

    @pytest.mark.asyncio
    async def test_batch_reject_writes_decision(self, http):
        c, db = http
        r = await _mk_approving(db)
        resp = await c.post("/api/v1/reviews/batch/reject", json={
            "review_ids": [r.id], "reason": "质量不过",
        })
        assert resp.status_code == 207
        await db.refresh(r)
        rr = r.metadata_json["review_result"]
        assert rr["decision"] == "reject"
        assert rr["reason"] == "质量不过"
