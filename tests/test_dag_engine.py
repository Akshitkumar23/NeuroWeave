"""
Unit Test Suite for DAGEngine.
Covers topological sorting, cycle detection, execution waves, parallel execution,
cascade failure isolation, retries, dynamic task injection, and red/green metrics.
"""

import asyncio
import unittest
from core.dag_engine import DAGEngine, DAGCycleError, TaskStatus
from core.state_manager import StateManager


class TestDAGEngine(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.state = StateManager("test_session_dag")

    def test_topological_sort_linear(self):
        tasks = {
            "task_01": {"id": "task_01", "dependencies": []},
            "task_02": {"id": "task_02", "dependencies": ["task_01"]},
            "task_03": {"id": "task_03", "dependencies": ["task_02"]},
        }
        order = DAGEngine.topological_sort(tasks)
        self.assertEqual(order, ["task_01", "task_02", "task_03"])

    def test_topological_sort_diamond(self):
        tasks = {
            "A": {"id": "A", "dependencies": []},
            "B": {"id": "B", "dependencies": ["A"]},
            "C": {"id": "C", "dependencies": ["A"]},
            "D": {"id": "D", "dependencies": ["B", "C"]},
        }
        order = DAGEngine.topological_sort(tasks)
        self.assertEqual(order[0], "A")
        self.assertEqual(order[-1], "D")
        self.assertTrue(order.index("B") < order.index("D"))
        self.assertTrue(order.index("C") < order.index("D"))

    def test_topological_sort_cycle_detected(self):
        tasks = {
            "A": {"id": "A", "dependencies": ["C"]},
            "B": {"id": "B", "dependencies": ["A"]},
            "C": {"id": "C", "dependencies": ["B"]},
        }
        with self.assertRaises(DAGCycleError):
            DAGEngine.topological_sort(tasks)

    def test_topological_sort_self_dependency(self):
        tasks = {
            "A": {"id": "A", "dependencies": ["A"]},
        }
        with self.assertRaises(DAGCycleError):
            DAGEngine.topological_sort(tasks)

    def test_get_execution_waves(self):
        tasks = {
            "A1": {"id": "A1", "dependencies": []},
            "A2": {"id": "A2", "dependencies": []},
            "B1": {"id": "B1", "dependencies": ["A1"]},
            "B2": {"id": "B2", "dependencies": ["A1", "A2"]},
            "C1": {"id": "C1", "dependencies": ["B1", "B2"]},
        }
        waves = DAGEngine.get_execution_waves(tasks)
        self.assertEqual(len(waves), 3)
        self.assertCountEqual(waves[0], ["A1", "A2"])
        self.assertCountEqual(waves[1], ["B1", "B2"])
        self.assertEqual(waves[2], ["C1"])

    async def test_execute_dag_success(self):
        task_list = [
            {"id": "t1", "title": "Task 1", "dependencies": [], "assigned_agent": "researcher"},
            {"id": "t2", "title": "Task 2", "dependencies": ["t1"], "assigned_agent": "analyzer"},
        ]
        await self.state.update_tasks(task_list)

        executed = []
        async def mock_executor(task):
            executed.append(task["id"])
            return True, f"Output of {task['id']}", None

        engine = DAGEngine(state_manager=self.state, task_executor=mock_executor)
        result = await engine.execute_dag()

        self.assertEqual(executed, ["t1", "t2"])
        self.assertEqual(result["t1"]["status"], "completed")
        self.assertEqual(result["t2"]["status"], "completed")
        
        summary = engine.get_execution_summary()
        self.assertTrue(summary["is_green"])
        self.assertEqual(summary["completed"], 2)
        self.assertEqual(summary["failed"], 0)

    async def test_execute_dag_cascade_failure_isolation(self):
        """If prerequisite t1 fails, dependent t2 should be marked failed (blocked)."""
        task_list = [
            {"id": "t1", "title": "Task 1", "dependencies": [], "assigned_agent": "researcher", "max_retries": 0},
            {"id": "t2", "title": "Task 2", "dependencies": ["t1"], "assigned_agent": "analyzer"},
        ]
        await self.state.update_tasks(task_list)

        async def failing_executor(task):
            if task["id"] == "t1":
                return False, None, "Simulated network failure"
            return True, "Output of t2", None

        engine = DAGEngine(state_manager=self.state, task_executor=failing_executor)
        result = await engine.execute_dag()

        self.assertEqual(result["t1"]["status"], "failed")
        self.assertEqual(result["t2"]["status"], "failed")
        self.assertIn("Prerequisite task 't1' failed", result["t2"]["error"])
        
        summary = engine.get_execution_summary()
        self.assertFalse(summary["is_green"])
        self.assertEqual(summary["failed"], 2)

    async def test_execute_dag_retry_mechanism(self):
        """Task should retry up to max_retries before completing."""
        task_list = [
            {"id": "t_retry", "title": "Task Retry", "dependencies": [], "assigned_agent": "researcher", "max_retries": 2},
        ]
        await self.state.update_tasks(task_list)

        attempts = 0
        async def flaky_executor(task):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                return False, None, "Transient timeout"
            return True, "Success after retry", None

        engine = DAGEngine(state_manager=self.state, task_executor=flaky_executor)
        result = await engine.execute_dag()

        self.assertEqual(result["t_retry"]["status"], "completed")
        self.assertEqual(attempts, 2)
        summary = engine.get_execution_summary()
        self.assertEqual(summary["retries"], 1)
        self.assertTrue(summary["is_green"])

    async def test_dynamic_task_injection(self):
        initial_tasks = [
            {"id": "t1", "title": "Initial Task", "dependencies": [], "assigned_agent": "researcher"},
        ]
        await self.state.update_tasks(initial_tasks)
        await self.state.set_task_status("t1", "completed", output="Initial findings")

        engine = DAGEngine(state_manager=self.state)
        
        new_tasks = [
            {"id": "t2_injected", "title": "Injected Task", "dependencies": ["t1"], "assigned_agent": "analyzer"},
        ]
        success, err = await engine.inject_tasks(new_tasks)
        self.assertTrue(success)
        self.assertIsNone(err)

        snapshot = await self.state.get_tasks_snapshot()
        self.assertIn("t2_injected", snapshot)
        self.assertEqual(snapshot["t1"]["status"], "completed")
        self.assertEqual(snapshot["t2_injected"]["status"], "pending")

    async def test_dynamic_task_injection_rejects_cycle(self):
        initial_tasks = [
            {"id": "t1", "title": "Initial Task", "dependencies": [], "assigned_agent": "researcher"},
        ]
        await self.state.update_tasks(initial_tasks)

        engine = DAGEngine(state_manager=self.state)
        
        # Injected task creating cycle with t1
        bad_tasks = [
            {"id": "t1", "dependencies": ["t2"]},
            {"id": "t2", "dependencies": ["t1"]},
        ]
        success, err = await engine.inject_tasks(bad_tasks)
        self.assertFalse(success)
        self.assertIn("Cycle detected", err)


if __name__ == "__main__":
    unittest.main()
