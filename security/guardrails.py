import re
import logging
from typing import Dict, Any, List
from urllib.parse import urlparse

logger = logging.getLogger("neuroweave.guardrails")

class SecurityGuardrails:
    # Prompt injection vectors
    INJECTION_PATTERNS = [
        r"(ignore\s+previous\s+instructions)",
        r"(system\s+prompt\s+override)",
        r"(you\s+are\s+now\s+freed)",
        r"(jailbreak)",
        r"(dan\s+mode)",
        r"(under\s+no\s+circumstances\s+follow)",
        r"(do\s+not\s+format\s+as\s+json)"
    ]
    
    # Blocked local IP/domain targets
    BLOCKED_SCHEMES = ["file", "gopher", "ftp"]
    BLOCKED_DOMAINS = ["localhost", "127.0.0.1", "0.0.0.0", "internal.network", "169.254.169.254"]

    # Restricted keywords in safe Python code execution
    BLOCKED_CODE_KEYWORDS = [
        "import os", "import sys", "import subprocess", "import shutil",
        "eval(", "exec(", "open(", "write(", "builtins", "__import__",
        "rmtree", "system(", "popen(", "os.", "sys."
    ]

    @classmethod
    def sanitize_user_query(cls, query: str) -> str:
        """
        Scans and sanitizes queries against potential prompt injection attacks.
        """
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.warning(f"Security Alert: Potential prompt injection attempt intercepted: {pattern}")
                # Neutralize injection by stripping dangerous instructions
                query = re.sub(pattern, "[GUARDRAILS CLEARED PHRASE]", query, flags=re.IGNORECASE)
        return query

    @classmethod
    def is_url_safe(cls, url: str) -> bool:
        """
        Prevents Server-Side Request Forgery (SSRF) and malicious file access.
        """
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            hostname = parsed.hostname
            
            if scheme in cls.BLOCKED_SCHEMES:
                logger.warning(f"Security Intercept: Blocked scheme '{scheme}' in URL: {url}")
                return False
                
            if hostname:
                hostname = hostname.lower()
                if hostname in cls.BLOCKED_DOMAINS or any(domain in hostname for domain in [".local", ".lan"]):
                    logger.warning(f"Security Intercept: Blocked malicious/local domain target: {hostname}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Error parsing URL safety: {e}")
            return False

    @classmethod
    def is_code_safe(cls, code: str) -> bool:
        """
        Enforces a secure static analysis layer to prevent file/process operations
        within the dynamic Python Executor tool.
        """
        # Strip comments
        stripped_code = re.sub(r"#.*", "", code)
        
        # 1. Check existing keyword-based blocklist
        for keyword in cls.BLOCKED_CODE_KEYWORDS:
            if keyword in stripped_code:
                logger.warning(f"Security Intercept: Unsafe keyword '{keyword}' detected in submitted code.")
                return False
                
        # 2. Robust Regex checks for unsafe imports
        # Detects import statement variations with arbitrary whitespace: e.g. "import os", "import   os", etc.
        # Detects "from os import", "from sys import", etc.
        unsafe_modules = r"(os|sys|subprocess|shutil|builtins|socket|requests|urllib|platform|ctypes|pty|posix|signal)"
        import_pattern = rf"\b(import|from)\s+{unsafe_modules}\b"
        if re.search(import_pattern, stripped_code, re.IGNORECASE):
            logger.warning("Security Intercept: Unsafe module import detected via regex scanning.")
            return False
            
        # 3. Robust Regex checks for dunder attributes / breakout attempts
        # Block dunder lookups (like __subclasses__, __globals__, __builtins__, __import__)
        if re.search(r"__\w+__", stripped_code):
            logger.warning("Security Intercept: Dunder attribute/method access detected.")
            return False
            
        # 4. Check for variations of exec/eval/open/system/popen call syntax with whitespace/newlines
        unsafe_calls = r"(eval|exec|open|system|popen|shutil)\s*\("
        if re.search(unsafe_calls, stripped_code, re.IGNORECASE):
            logger.warning("Security Intercept: Unsafe function call pattern detected.")
            return False
            
        return True

    @classmethod
    def sanitize_output(cls, text: str) -> str:
        """
        Strips script blocks or other raw formatting injection vectors from generated content.
        """
        # Neutralize HTML script blocks
        sanitized = re.sub(r"<script.*?>.*?</script>", "[SCRIPT INTERCEPTED]", text, flags=re.IGNORECASE | re.DOTALL)
        return sanitized
