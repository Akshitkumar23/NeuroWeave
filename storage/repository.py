import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from storage.database import DatabaseManager

logger = logging.getLogger("neuroweave.repository")

class SessionRepository:
    """
    Implements a Repository Pattern isolating SQLite execution details.
    Runs async CRUD transactions via non-blocking connection instances.
    """
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def create_session(self, session_id: str, query: str) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = asyncio.get_event_loop().time()
                await conn.execute(
                    "INSERT INTO sessions (session_id, query, status, timestamp, metrics_json) VALUES (?, ?, ?, ?, ?)",
                    (session_id, query, "initialized", timestamp, "{}")
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error creating session record: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                # Delete related logs, reports, and traces to keep db clean
                await conn.execute("DELETE FROM execution_logs WHERE session_id = ?", (session_id,))
                await conn.execute("DELETE FROM reports WHERE session_id = ?", (session_id,))
                await conn.execute("DELETE FROM traces WHERE session_id = ?", (session_id,))
                await conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    async def update_session_status(self, session_id: str, status: str, metrics: Optional[Dict[str, Any]] = None) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                metrics_json = json.dumps(metrics or {})
                await conn.execute(
                    "UPDATE sessions SET status = ?, metrics_json = ? WHERE session_id = ?",
                    (status, metrics_json, session_id)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating session status: {e}")
            return False

    async def insert_report(self, session_id: str, content: str, confidence_score: float) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = asyncio.get_event_loop().time()
                await conn.execute(
                    "INSERT INTO reports (session_id, content, confidence_score, timestamp) VALUES (?, ?, ?, ?)",
                    (session_id, content, confidence_score, timestamp)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting report: {e}")
            return False

    async def insert_log(self, session_id: str, agent: str, message: str, type_str: str) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = asyncio.get_event_loop().time()
                await conn.execute(
                    "INSERT INTO execution_logs (session_id, timestamp, agent, message, type) VALUES (?, ?, ?, ?, ?)",
                    (session_id, timestamp, agent, message, type_str)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting log entry: {e}")
            return False

    async def insert_trace(
        self,
        session_id: str,
        task_id: str,
        agent: str,
        duration: float,
        success: bool,
        cost: float,
        tokens_in: int,
        tokens_out: int
    ) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = asyncio.get_event_loop().time()
                success_int = 1 if success else 0
                await conn.execute(
                    """INSERT INTO traces 
                       (session_id, task_id, agent, duration_sec, success, cost, tokens_input, tokens_output, timestamp) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, task_id, agent, duration, success_int, cost, tokens_in, tokens_out, timestamp)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting trace telemetry: {e}")
            return False

    async def get_session_report(self, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT content, confidence_score, timestamp FROM reports WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                    (session_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "content": row[0],
                            "confidence_score": row[1],
                            "timestamp": row[2]
                        }
        except Exception as e:
            logger.error(f"Error reading session report: {e}")
        return None

    async def get_session_logs(self, session_id: str) -> List[Dict[str, Any]]:
        logs = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT agent, message, type, timestamp FROM execution_logs WHERE session_id = ? ORDER BY timestamp ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        logs.append({
                            "agent": r[0],
                            "message": r[1],
                            "type": r[2],
                            "timestamp": r[3]
                        })
        except Exception as e:
            logger.error(f"Error reading session logs: {e}")
        return logs

    async def list_sessions(self) -> List[Dict[str, Any]]:
        sessions = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT session_id, query, status, timestamp, metrics_json FROM sessions ORDER BY timestamp DESC"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        sessions.append({
                            "session_id": r[0],
                            "query": r[1],
                            "status": r[2],
                            "timestamp": r[3],
                            "metrics": json.loads(r[4] or "{}")
                        })
        except Exception as e:
            logger.error(f"Error listing session history: {e}")
        return sessions
