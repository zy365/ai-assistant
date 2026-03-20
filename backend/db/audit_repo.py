from uuid import UUID
from db.database import get_pool


class AuditRepo:

    async def log_tool_call(
        self,
        session_id: UUID,
        operator_id: str,       # 当前会话人ID
        operator_name: str,     # 当前会话人姓名
        tool_name: str,
        params: dict,
        result: dict | None,
        status: str,
        duration_ms: int,
        roles_at_call: list[str],
        scope_injected: dict,
        permission_rule: str,
    ) -> None:
        import json
        pool = await get_pool()
        await pool.execute(
            """INSERT INTO tool_logs
               (session_id, operator_id, operator_name, tool_name, params, result,
                status, duration_ms, roles_at_call, scope_injected, permission_rule)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
            session_id,
            operator_id,
            operator_name,
            tool_name,
            json.dumps(params),
            json.dumps(result) if result else None,
            status,
            duration_ms,
            roles_at_call,
            json.dumps(scope_injected),
            permission_rule,
        )

    async def list_tool_calls(
        self,
        operator_id: str,
        tool_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        pool = await get_pool()
        if tool_name:
            rows = await pool.fetch(
                """SELECT * FROM tool_logs
                   WHERE operator_id=$1 AND tool_name=$2
                   ORDER BY called_at DESC LIMIT $3""",
                operator_id, tool_name, limit,
            )
        else:
            rows = await pool.fetch(
                """SELECT * FROM tool_logs
                   WHERE operator_id=$1
                   ORDER BY called_at DESC LIMIT $2""",
                operator_id, limit,
            )
        return [dict(r) for r in rows]


audit_repo = AuditRepo()
