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
        Asynchronously creates schemas.
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
            
            # 2. Reports table
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
            
            # 3. Execution Logs table (for streaming and reloading)
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
            
            # 4. Telemetry Traces table
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
            
            await conn.commit()
            logger.info("Database schemas created successfully.")
