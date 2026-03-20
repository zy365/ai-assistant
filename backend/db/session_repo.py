import uuid
from uuid import UUID
from db.database import get_pool


class SessionRepo:

    async def create(self, operator_id: str, title: str = "") -> dict:
        pool = await get_pool()
        row = await pool.fetchrow(
            """INSERT INTO sessions (operator_id, title)
               VALUES ($1, $2) RETURNING *""",
            operator_id, title or "新对话",
        )
        return dict(row)

    async def list_by_operator(self, operator_id: str, limit: int = 50) -> list[dict]:
        pool = await get_pool()
        rows = await pool.fetch(
            """SELECT * FROM sessions
               WHERE operator_id = $1 AND status = 'active'
               ORDER BY updated_at DESC LIMIT $2""",
            operator_id, limit,
        )
        return [dict(r) for r in rows]

    async def get(self, session_id: UUID) -> dict | None:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT * FROM sessions WHERE id = $1", session_id
        )
        return dict(row) if row else None

    async def update_title(self, session_id: UUID, title: str) -> None:
        pool = await get_pool()
        await pool.execute(
            "UPDATE sessions SET title=$1, updated_at=now() WHERE id=$2",
            title, session_id,
        )

    async def touch(self, session_id: UUID) -> None:
        pool = await get_pool()
        await pool.execute(
            "UPDATE sessions SET updated_at=now() WHERE id=$1", session_id
        )

    async def archive(self, session_id: UUID) -> None:
        pool = await get_pool()
        await pool.execute(
            "UPDATE sessions SET status='archived', updated_at=now() WHERE id=$1",
            session_id,
        )

    async def delete(self, session_id: UUID) -> None:
        pool = await get_pool()
        await pool.execute("DELETE FROM sessions WHERE id=$1", session_id)

    async def save_selected_customer(
        self, session_id: uuid.UUID, user_id: str, user_name: str
    ) -> None:
        """把用户选定的客户持久化到 session，后续轮次自动带上"""
        pool = await get_pool()
        await pool.execute(
            """UPDATE sessions
               SET selected_user_id=$1, selected_user_name=$2, updated_at=now()
               WHERE id=$3""",
            user_id, user_name, session_id,
        )

    async def get_selected_customer(self, session_id: uuid.UUID) -> dict | None:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT selected_user_id, selected_user_name FROM sessions WHERE id=$1",
            session_id,
        )
        if not row or not row["selected_user_id"]:
            return None
        return {"userId": row["selected_user_id"], "userName": row["selected_user_name"]}


class MessageRepo:

    async def add(self, session_id: UUID, operator_id: str, role: str, content: str) -> dict:
        pool = await get_pool()
        row = await pool.fetchrow(
            """INSERT INTO messages (session_id, operator_id, role, content)
               VALUES ($1, $2, $3, $4) RETURNING *""",
            session_id, operator_id, role, content,
        )
        return dict(row)

    async def list_by_session(self, session_id: UUID, limit: int = 20) -> list[dict]:
        pool = await get_pool()
        rows = await pool.fetch(
            """SELECT * FROM messages
               WHERE session_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            session_id, limit,
        )
        return [dict(r) for r in reversed(rows)]

    async def search(self, operator_id: str, keyword: str, limit: int = 20) -> list[dict]:
        pool = await get_pool()
        rows = await pool.fetch(
            """SELECT m.* FROM messages m
               JOIN sessions s ON s.id = m.session_id
               WHERE s.operator_id = $1 AND m.content ILIKE $2
               ORDER BY m.created_at DESC LIMIT $3""",
            operator_id, f"%{keyword}%", limit,
        )
        return [dict(r) for r in rows]


session_repo = SessionRepo()
message_repo = MessageRepo()
