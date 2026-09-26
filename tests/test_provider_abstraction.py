import os
import unittest
from unittest.mock import patch, AsyncMock
import httpx
from core.model_router import ModelRouter

class TestProviderAbstraction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_safe_status_reporting_no_key(self):
        """When no API key is provided, safe status reports ZERO_API without secrets."""
        for key in ["LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY"]:
            os.environ.pop(key, None)
        router = ModelRouter()
        status = router.get_status()
        self.assertEqual(status["llm_configured"], "NO")
        self.assertEqual(status["provider"], "none")
        self.assertEqual(status["model"], "none")
        self.assertEqual(status["mode"], "ZERO_API")
        self.assertNotIn("key", status)
        self.assertNotIn("api_key", status)

    def test_safe_status_reporting_with_key(self):
        """When API key is provided, status reports provider & model without leaking the key."""
        os.environ["LLM_PROVIDER"] = "groq"
        os.environ["GROQ_API_KEY"] = "gsk_testsecretkey123456789"
        os.environ["LLM_MODEL"] = "llama-3.3-70b-versatile"
        router = ModelRouter()
        status = router.get_status()
        self.assertEqual(status["llm_configured"], "YES")
        self.assertEqual(status["provider"], "groq")
        self.assertEqual(status["model"], "llama-3.3-70b-versatile")
        self.assertEqual(status["mode"], "REAL_LLM")
        self.assertNotIn("gsk_testsecretkey123456789", str(status))

    def test_key_sanitization_in_errors(self):
        """Error messages containing API keys or bearer tokens must be strictly redacted."""
        raw_msg = (
            "Failed call to https://api.groq.com with key gsk_abc123456789xyz "
            "and Google key AIzaSyA1b2C3d4E5f6G7h8I9j0 and Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
        )
        sanitized = ModelRouter._sanitize_error_message(raw_msg)
        self.assertNotIn("gsk_abc123456789xyz", sanitized)
        self.assertNotIn("AIzaSyA1b2C3d4E5f6G7h8I9j0", sanitized)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", sanitized)
        self.assertIn("***REDACTED***", sanitized)

    async def test_fallback_on_auth_failure_401(self):
        """Invalid API key (HTTP 401) should log sanitized error and fallback gracefully to Zero-API."""
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "AIzaSyFakeKeyInvalid401"
        router = ModelRouter()

        req = httpx.Request("POST", "https://generativelanguage.googleapis.com")
        resp = httpx.Response(401, request=req, text="Unauthorized: Invalid API key AIzaSyFakeKeyInvalid401")
        err = httpx.HTTPStatusError("401 Unauthorized", request=req, response=resp)

        with patch.object(router, "_call_gemini_api", side_effect=err):
            response = await router.call_llm("Explain quantum computing", task_type="reasoning")
            self.assertTrue(response["success"])
            self.assertTrue(response["metadata"]["used_fallback"])
            self.assertEqual(response["metadata"]["error_type"], "auth_failure")
            self.assertEqual(response["metadata"]["mode"], "ZERO_API")
            self.assertGreater(len(response["content"]), 10)

    async def test_fallback_on_rate_limit_429(self):
        """Rate limit (HTTP 429) should log sanitized error and fallback gracefully to Zero-API."""
        os.environ["LLM_PROVIDER"] = "groq"
        os.environ["GROQ_API_KEY"] = "gsk_fakelimitedkey429"
        router = ModelRouter()

        req = httpx.Request("POST", "https://api.groq.com")
        resp = httpx.Response(429, request=req, text="Rate limit exceeded. Please wait.")
        err = httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)

        with patch.object(router, "_call_groq_api", side_effect=err):
            response = await router.call_llm("Compare Python and Go", task_type="general")
            self.assertTrue(response["success"])
            self.assertTrue(response["metadata"]["used_fallback"])
            self.assertEqual(response["metadata"]["error_type"], "rate_limit")
            self.assertEqual(response["metadata"]["mode"], "ZERO_API")
            self.assertGreater(len(response["content"]), 10)

    async def test_fallback_on_timeout(self):
        """Network timeout should log warning and fallback gracefully to Zero-API."""
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "AIzaSyValidFormatKeyTimeout"
        router = ModelRouter()

        req = httpx.Request("POST", "https://generativelanguage.googleapis.com")
        err = httpx.TimeoutException("Connection timed out after 15s", request=req)

        with patch.object(router, "_call_gemini_api", side_effect=err):
            response = await router.call_llm("What is photosynthesis?", task_type="fast")
            self.assertTrue(response["success"])
            self.assertTrue(response["metadata"]["used_fallback"])
            self.assertEqual(response["metadata"]["error_type"], "timeout")
            self.assertEqual(response["metadata"]["mode"], "ZERO_API")
            self.assertGreater(len(response["content"]), 10)

    async def test_fallback_on_provider_down_503(self):
        """Service unavailable (HTTP 503) should trigger fallback gracefully."""
        os.environ["LLM_PROVIDER"] = "groq"
        os.environ["GROQ_API_KEY"] = "gsk_serviceunavailable"
        router = ModelRouter()

        req = httpx.Request("POST", "https://api.groq.com")
        resp = httpx.Response(503, request=req, text="Service Unavailable")
        err = httpx.HTTPStatusError("503 Service Unavailable", request=req, response=resp)

        with patch.object(router, "_call_groq_api", side_effect=err):
            response = await router.call_llm("Analyze this architecture", task_type="code")
            self.assertTrue(response["success"])
            self.assertTrue(response["metadata"]["used_fallback"])
            self.assertEqual(response["metadata"]["error_type"], "provider_error")
            self.assertEqual(response["metadata"]["mode"], "ZERO_API")
            self.assertGreater(len(response["content"]), 10)

if __name__ == "__main__":
    unittest.main()
