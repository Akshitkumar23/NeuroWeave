"""
NeuroWeave API, UI Static Assets and SSE Real-time Streaming Tests.
Verifies production server endpoints, SSE lifecycle, and UI dashboard loading.
"""

import os
import sys
import json
import asyncio
import unittest
from fastapi.testclient import TestClient

# Ensure root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
import api.routes as routes
from storage.database import DatabaseManager

class TestApiSseAndUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "storage/test_api_ui.db"
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass
        cls.db_manager = DatabaseManager(db_path=cls.test_db)
        asyncio.run(cls.db_manager.initialize_tables())
        routes.db_manager = cls.db_manager
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def test_01_ui_index_and_static_assets(self):
        """Verify UI index.html, styles.css, and app.js load properly."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("NeuroWeave", response.text)
        self.assertIn("dark-theme", response.text)

        css_resp = self.client.get("/styles.css")
        self.assertEqual(css_resp.status_code, 200)
        self.assertIn("font-family", css_resp.text.lower())

        js_resp = self.client.get("/app.js")
        self.assertEqual(js_resp.status_code, 200)
        self.assertIn("EventSource", js_resp.text)

    def test_02_post_analysis_and_sse_stream(self):
        """Verify POST /api/analyze creates session and /api/stream yields SSE events."""
        payload = {
            "query": "What is Model Context Protocol (MCP)?",
            "division": "engineering"
        }
        res = self.client.post("/api/analyze", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        session_id = data.get("session_id")
        self.assertIsNotNone(session_id)

        with self.client.stream("GET", f"/api/stream/{session_id}") as stream_resp:
            self.assertEqual(stream_resp.status_code, 200)
            self.assertIn("text/event-stream", stream_resp.headers.get("content-type", ""))
            
            events = []
            for line in stream_resp.iter_lines():
                if line.startswith("data: "):
                    ev_data = json.loads(line[6:])
                    events.append(ev_data)
                    if ev_data.get("status") in ["completed", "failed"]:
                        break
                if len(events) > 30:
                    break
            
            self.assertGreater(len(events), 0, "No SSE events received from stream!")
            final_event = events[-1]
            self.assertIn(final_event.get("status"), ["completed", "running"])

    def test_03_settings_keys_safe_redaction(self):
        """Verify POST /api/save-key saves key and /api/key-status reports zero_api without leaking secrets."""
        res = self.client.post("/api/save-key", json={"api_key": "AIzaSyFakeKey12345ForTestingOnly", "provider": "gemini"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("success"))
        self.assertNotIn("AIzaSyFakeKey12345ForTestingOnly", str(res.json()))

        status_res = self.client.get("/api/key-status")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json().get("mode"), "zero_api")
        self.assertNotIn("AIzaSyFakeKey12345ForTestingOnly", str(status_res.json()))

    def test_04_stream_nonexistent_session_returns_404(self):
        """Verify querying stream for non-existent session returns 404."""
        res = self.client.get("/api/stream/non-existent-session-id-0000")
        self.assertEqual(res.status_code, 404)

if __name__ == "__main__":
    unittest.main()
