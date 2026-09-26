"""
Unit Test Suite for StateManager.
Covers in-memory state tracking, snapshot rollbacks, JSON serialization,
SQLite schema migrations verification, and database session recovery.
"""

import os
import unittest
from core.state_manager import StateManager
from storage.database import DatabaseManager


class TestStateManager(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.test_db_path = "storage/test_state_mgr.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.db = DatabaseManager(self.test_db_path)
        await self.db.initialize_tables()

    async def asyncTearDown(self):
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except Exception:
                pass

    async def test_session_lifecycle_and_task_updates(self):
        mgr = StateManager("sess_001")
        await mgr.initialize_session("What is KV cache quantization?")
        self.assertEqual(mgr.query, "What is KV cache quantization?")
        self.assertEqual(mgr.status, "running")

        tasks = [
            {"id": "t1", "title": "Research", "assigned_agent": "researcher", "dependencies": []},
            {"id": "t2", "title": "Analyze", "assigned_agent": "analyzer", "dependencies": ["t1"]}
        ]
        await mgr.update_tasks(tasks)

        snapshot = await mgr.get_tasks_snapshot()
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(snapshot["t1"]["status"], "pending")

        # Update status
        await mgr.set_task_status("t1", "running")
        snapshot = await mgr.get_tasks_snapshot()
        self.assertEqual(snapshot["t1"]["status"], "running")

        await mgr.set_task_status("t1", "completed", output="KV cache findings")
        snapshot = await mgr.get_tasks_snapshot()
        self.assertEqual(snapshot["t1"]["status"], "completed")
        self.assertEqual(snapshot["t1"]["output"], "KV cache findings")

    async def test_snapshot_rollback(self):
        mgr = StateManager("sess_rollback")
        await mgr.initialize_session("Query")
        
        # State at point 1: t1 completed
        await mgr.update_tasks([{"id": "t1", "title": "Task 1", "dependencies": []}])
        await mgr.set_task_status("t1", "completed", output="Valid output 1")
        
        # State at point 2: status changed to failed
        await mgr.set_task_status("t1", "failed", error="Error details")
        self.assertEqual(mgr.tasks["t1"]["status"], "failed")

        # Rollback restores previous completed checkpoint
        success = await mgr.rollback()
        self.assertTrue(success)
        
        state_dict = await mgr.get_state_dict()
        self.assertEqual(state_dict["tasks"]["t1"]["status"], "completed")
        self.assertEqual(state_dict["tasks"]["t1"]["output"], "Valid output 1")

    async def test_serialization_and_deserialization(self):
        mgr = StateManager("sess_serial")
        await mgr.initialize_session("Serialization query")
        await mgr.update_tasks([{"id": "t1", "title": "Task 1", "dependencies": []}])
        await mgr.add_confidence_score(0.88)
        await mgr.add_log("system", "Test log message", "info")

        # Serialize
        json_data = mgr.to_json()
        self.assertIsInstance(json_data, str)
        self.assertIn("Serialization query", json_data)

        # Deserialize
        restored = StateManager.from_json(json_data)
        self.assertEqual(restored.session_id, "sess_serial")
        self.assertEqual(restored.query, "Serialization query")
        self.assertEqual(len(restored.tasks), 1)
        self.assertEqual(restored.confidence_history, [0.88])

    async def test_sqlite_schema_migrations_and_recovery(self):
        # 1. Run migrations
        migration_ok = await StateManager.verify_and_run_migrations(self.db)
        self.assertTrue(migration_ok)

        # 2. Save session and checkpoint to database
        mgr = StateManager("sess_recoverable")
        await mgr.initialize_session("Crash recovery test query")
        await mgr.update_tasks([
            {"id": "t_done", "title": "Done Task", "dependencies": [], "status": "completed", "output": "Recovered output"},
            {"id": "t_running", "title": "Interrupted Task", "dependencies": ["t_done"], "status": "running"}
        ])
        
        saved = await mgr.save_checkpoint_to_db(self.db)
        self.assertTrue(saved)

        # 3. Simulate crash and recover session
        recovered = await StateManager.recover_session("sess_recoverable", self.db)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.session_id, "sess_recoverable")
        self.assertEqual(recovered.query, "Crash recovery test query")
        
        tasks = recovered.tasks
        self.assertEqual(tasks["t_done"]["status"], "completed")
        self.assertEqual(tasks["t_done"]["output"], "Recovered output")
        # Interrupted running task must be reset to pending for DAG engine re-execution
        self.assertEqual(tasks["t_running"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
