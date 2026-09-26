import json
import logging
import asyncio
import time
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
                timestamp = time.time()
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, query, status, timestamp, metrics_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        query = excluded.query,
                        status = excluded.status,
                        timestamp = excluded.timestamp
                    """,
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
                timestamp = time.time()
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
                timestamp = time.time()
                # Insert into canonical execution_logs
                await conn.execute(
                    "INSERT INTO execution_logs (session_id, timestamp, agent, message, type) VALUES (?, ?, ?, ?, ?)",
                    (session_id, timestamp, agent, message, type_str)
                )
                # Also record in logs table
                await conn.execute(
                    "INSERT INTO logs (session_id, timestamp, agent, message, type) VALUES (?, ?, ?, ?, ?)",
                    (session_id, timestamp, agent, message, type_str)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting log entry: {e}")
            return False

    async def get_session_logs(self, session_id: str) -> List[Dict[str, Any]]:
        logs = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT timestamp, agent, message, type FROM logs WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        logs.append({
                            "timestamp": r[0],
                            "agent": r[1],
                            "message": r[2],
                            "type": r[3]
                        })
        except Exception as e:
            logger.error(f"Error reading session logs: {e}")
        return logs

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
                timestamp = time.time()
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

    async def get_session_traces(self, session_id: str) -> List[Dict[str, Any]]:
        traces = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT task_id, agent, duration_sec, success, cost, tokens_input, tokens_output, timestamp FROM traces WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        traces.append({
                            "task_id": r[0],
                            "agent": r[1],
                            "duration_sec": r[2],
                            "success": bool(r[3]),
                            "cost": r[4],
                            "tokens_input": r[5],
                            "tokens_output": r[6],
                            "timestamp": r[7]
                        })
        except Exception as e:
            logger.error(f"Error reading session traces: {e}")
        return traces

    async def insert_task(
        self,
        task_id: str,
        session_id: str,
        description: str,
        assigned_agent: str,
        status: str = "pending",
        output: Optional[str] = None,
        error: Optional[str] = None,
        dependencies: Optional[List[str]] = None
    ) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = time.time()
                dep_json = json.dumps(dependencies or [])
                await conn.execute(
                    """INSERT INTO tasks 
                       (task_id, session_id, description, assigned_agent, status, output, error, dependencies_json, timestamp) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (task_id, session_id, description, assigned_agent, status, output, error, dep_json, timestamp)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting task: {e}")
            return False

    async def get_session_tasks(self, session_id: str) -> List[Dict[str, Any]]:
        tasks = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT task_id, description, assigned_agent, status, output, error, dependencies_json, timestamp FROM tasks WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        tasks.append({
                            "task_id": r[0],
                            "description": r[1],
                            "assigned_agent": r[2],
                            "status": r[3],
                            "output": r[4],
                            "error": r[5],
                            "dependencies": json.loads(r[6] or "[]"),
                            "timestamp": r[7]
                        })
        except Exception as e:
            logger.error(f"Error reading session tasks: {e}")
        return tasks

    async def insert_metric(
        self,
        session_id: str,
        metric_name: str,
        metric_value: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = time.time()
                meta_json = json.dumps(metadata or {})
                await conn.execute(
                    "INSERT INTO metrics (session_id, metric_name, metric_value, metadata_json, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (session_id, metric_name, metric_value, meta_json, timestamp)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting metric: {e}")
            return False

    async def get_session_metrics(self, session_id: str) -> List[Dict[str, Any]]:
        metrics = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT metric_name, metric_value, metadata_json, timestamp FROM metrics WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        metrics.append({
                            "metric_name": r[0],
                            "metric_value": r[1],
                            "metadata": json.loads(r[2] or "{}"),
                            "timestamp": r[3]
                        })
        except Exception as e:
            logger.error(f"Error reading session metrics: {e}")
        return metrics

    async def insert_document(
        self,
        session_id: str,
        document_name: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = time.time()
                meta_json = json.dumps(metadata or {})
                await conn.execute(
                    "INSERT INTO documents (session_id, document_name, content, metadata_json, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (session_id, document_name, content, meta_json, timestamp)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting document: {e}")
            return False

    async def get_session_documents(self, session_id: str) -> List[Dict[str, Any]]:
        documents = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT document_name, content, metadata_json, timestamp FROM documents WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        documents.append({
                            "document_name": r[0],
                            "content": r[1],
                            "metadata": json.loads(r[2] or "{}"),
                            "timestamp": r[3]
                        })
        except Exception as e:
            logger.error(f"Error reading session documents: {e}")
        return documents

    async def insert_feedback(
        self,
        session_id: str,
        user_feedback: str,
        rating: Optional[int] = None
    ) -> bool:
        try:
            async with await self.db.get_connection() as conn:
                timestamp = time.time()
                await conn.execute(
                    "INSERT INTO feedback (session_id, user_feedback, rating, timestamp) VALUES (?, ?, ?, ?)",
                    (session_id, user_feedback, rating, timestamp)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error inserting feedback: {e}")
            return False

    async def get_session_feedback(self, session_id: str) -> List[Dict[str, Any]]:
        feedbacks = []
        try:
            async with await self.db.get_connection() as conn:
                async with conn.execute(
                    "SELECT user_feedback, rating, timestamp FROM feedback WHERE session_id = ? ORDER BY id ASC",
                    (session_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        feedbacks.append({
                            "user_feedback": r[0],
                            "rating": r[1],
                            "timestamp": r[2]
                        })
        except Exception as e:
            logger.error(f"Error reading session feedback: {e}")
        return feedbacks

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

    async def search_prior_reports(self, query_terms: List[str], current_session_id: str = "", limit: int = 2) -> List[Dict[str, Any]]:
        """
        Cross-Report Knowledge Memory: Searches prior completed session reports
        in SQLite to find relevant historical findings and cross-dossier intelligence.
        """
        results = []
        if not query_terms:
            return results
        try:
            async with await self.db.get_connection() as conn:
                conditions = []
                params = []
                for term in query_terms[:5]:
                    cleaned = term.strip().lower()
                    if len(cleaned) > 3:
                        conditions.append("(LOWER(s.query) LIKE ? OR LOWER(r.content) LIKE ?)")
                        params.extend([f"%{cleaned}%", f"%{cleaned}%"])
                
                if not conditions:
                    return results
                
                where_clause = " OR ".join(conditions)
                sql = f"""
                    SELECT r.session_id, s.query, r.content, r.confidence_score, r.timestamp
                    FROM reports r
                    JOIN sessions s ON r.session_id = s.session_id
                    WHERE ({where_clause})
                """
                if current_session_id:
                    sql += " AND r.session_id != ?"
                    params.append(current_session_id)
                sql += " ORDER BY r.timestamp DESC LIMIT ?"
                params.append(limit)

                async with conn.execute(sql, tuple(params)) as cursor:
                    rows = await cursor.fetchall()
                    current_t = time.time()
                    for r in rows:
                        content_str = str(r[2] or "")
                        report_time = float(r[4] or 0.0)
                        # Staleness threshold: 30 days (2,592,000 seconds)
                        age_days = (current_t - report_time) / 86400.0 if report_time > 0 else 0
                        status = "Stale Historical Context" if age_days > 30 else "Verified Historical Evidence"
                        results.append({
                            "session_id": r[0],
                            "query": r[1],
                            "excerpt": content_str[:350] + ("..." if len(content_str) > 350 else ""),
                            "confidence_score": r[3],
                            "timestamp": report_time,
                            "age_days": round(age_days, 1),
                            "status": status
                        })
        except Exception as e:
            logger.error(f"Error searching prior reports: {e}")
        return results

