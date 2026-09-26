import os
import sqlite3
import logging
import aiosqlite
from typing import Optional

logger = logging.getLogger("neuroweave.database")

class AsyncConnectionContext:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    async def __aenter__(self) -> aiosqlite.Connection:
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            await self.conn.close()

class DatabaseManager:
    """
    Handles asynchronous SQLite initialization and query context structures.
    Uses 'aiosqlite' for non-blocking I/O.
    """
    def __init__(self, db_path: str = "storage/neuroweave.db"):
        self.db_path = db_path
        self._ensure_storage()

    def _ensure_storage(self):
        folder = os.path.dirname(self.db_path)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

    async def get_connection(self) -> AsyncConnectionContext:
        """
        Returns an async context manager for SQLite transactions.
        """
        return AsyncConnectionContext(self.db_path)


    async def initialize_tables(self):
        """
        Asynchronously creates schemas and runs migrations.
        """
        logger.info("Initializing SQLite database schemas.")
        async with await self.get_connection() as conn:
            # 1. Sessions table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metrics_json TEXT
                )
            """)
            
            # 2. Tasks table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    description TEXT,
                    assigned_agent TEXT,
                    status TEXT NOT NULL,
                    output TEXT,
                    error TEXT,
                    dependencies_json TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)

            # 3. Logs tables (both canonical 'logs' and 'execution_logs' for compatibility)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    agent TEXT NOT NULL,
                    message TEXT NOT NULL,
                    type TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    agent TEXT NOT NULL,
                    message TEXT NOT NULL,
                    type TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # 4. Metrics & Traces tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    metadata_json TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    task_id TEXT,
                    agent TEXT NOT NULL,
                    duration_sec REAL NOT NULL,
                    success INTEGER NOT NULL,
                    cost REAL NOT NULL,
                    tokens_input INTEGER,
                    tokens_output INTEGER,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)

            # 5. Documents table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    document_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)

            # 6. Feedback table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    user_feedback TEXT NOT NULL,
                    rating INTEGER,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # 7. Reports table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence_score REAL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            
            # Schema migrations check / indices
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_session ON logs(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_logs_session ON execution_logs(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_session ON metrics(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_session ON documents(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_session ON reports(session_id);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_session ON traces(session_id);")

            await conn.commit()
            logger.info("Database schemas and migration indices verified successfully.")

    async def run_migrations(self):
        """
        Executes idempotent schema migrations.
        """
        await self.initialize_tables()

    # Convenience alias
    initialize = initialize_tables
