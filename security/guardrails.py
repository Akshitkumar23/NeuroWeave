import re
import logging
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("neuroweave.guardrails")

class SecurityGuardrails:
    # Prompt injection vectors
    INJECTION_PATTERNS = [
        r"(ignore\s+(?:all\s+)?(?:previous\s+)?instructions)",
        r"(system\s+(?:prompt\s+)?override)",
        r"(you\s+are\s+now\s+freed)",
        r"(jailbreak)",
        r"(dan\s+mode|you\s+are\s+now\s+dan)",
        r"(under\s+no\s+circumstances\s+follow)",
        r"(do\s+not\s+format\s+as\s+json)",
        r"(<script.*?>.*?</script>)",
        r"(reveal\s+(?:all\s+)?(?:api\s+)?keys?|leak\s+(?:the\s+)?(?:private\s+)?prompt|print\s+(?:all\s+)?(?:secret\s+)?keys?)",
        r"(drop\s+table\b|;\s*--)",
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
        Fences untrusted instruction vectors strictly as inert data without destroying legitimate query context.
        """
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.warning(f"Security Alert: Potential prompt injection attempt intercepted: {pattern}")
                # Neutralize injection vector and isolate strictly as inert data
                query = re.sub(pattern, "<untrusted_data>[GUARDRAILS CLEARED PHRASE]</untrusted_data>", query, flags=re.IGNORECASE)
        return query

    @classmethod
    def is_prompt_injection(cls, query: str) -> Tuple[bool, str]:
        """
        Classifies whether an input is an adversarial instruction, system override,
        delimiter injection, role impersonation, or secret extraction attack.
        """
        q_lower = query.lower()
        
        # Direct override / delimiter patterns
        extended_patterns = [
            (r"(ignore\s+(?:all\s+)?(?:previous\s+)?instructions)", "Direct Instruction Override"),
            (r"(system\s+(?:prompt\s+)?override)", "System Prompt Override"),
            (r"(\[system_override\]|<system_override>|###\s*system\s*override)", "Delimiter Injection"),
            (r"(ignore\s+(?:all\s+)?(?:safety\s+|security\s+)?(?:restrictions?|guardrails?|policies?|controls?|rules?|instructions?))", "Safety Directive Bypass"),
            (r"(reveal|output|print|leak|show|dump|get)\s+(?:all\s+)?(?:the\s+|your\s+|any\s+|raw\s+|system\s+|database\s+|internal\s+|stored\s+)*.*?(passwords?|credentials?|secrets?|(?:api[\s_]?|private\s+|secret\s+|encryption\s+|master\s+)?keys?|connection\s+string|config(?:uration)?(?:\s+file)?)", "System Asset Extraction Attempt"),
            (r"(secret\s+admin\s+passwords?|admin\s+passwords?)", "Privileged Data Extraction Attempt"),
            (r"(you\s+are\s+now\s+freed|you\s+are\s+now\s+dan|jailbreak)", "Jailbreak / Persona Hijack"),
            (r"(act\s+as\s+an\s+unrestricted\s+ai|bypass\s+(?:all\s+)?guardrails)", "Safety Directive Bypass"),
            (r"(under\s+no\s+circumstances\s+follow)", "Negative Constraint Injection"),
            (r"(<script.*?>.*?</script>)", "XSS Payload Injection"),
            (r"(drop\s+table\b|;\s*--)", "SQL Injection Vector"),
            # Phase 6.4 Fix #6: Credential exfiltration patterns (compound-verb attacks)
            (r"(extract\s+and\s+(?:dump|export|list|output|reveal|show)).*?(passwords?|credentials?|secrets?|(?:api[\s_]?|private\s+)?keys?)", "Extraction Directive — Compound Verb"),
            (r"(list\s+all\s+(?:credentials?|secrets?|passwords?|(?:api[\s_]?|private\s+)?keys?))", "Asset Enumeration Attempt"),
            (r"(export\s+all\s+(?:(?:private|customer|user|internal|confidential|sensitive)\s+){1,3}(?:data|records?|information|files?))", "Data Exfiltration Attack"),
            (r"(dump\s+(?:all\s+)?(?:internal\s+)?(?:database\s+)?passwords?)", "Database Extraction Attempt"),
            (r"(reveal\s+(?:all\s+)?stored\s+(?:credentials?|passwords?|secrets?|keys?))", "Stored Data Extraction Attempt"),
        ]
        
        for pattern, reason in extended_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return True, reason
                
        return False, ""

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


def is_prompt_injection(query: str) -> bool:
    """Convenience function returning boolean indicating if query is a prompt injection attempt."""
    is_inj, _ = SecurityGuardrails.is_prompt_injection(query)
    return is_inj


def sanitize_input(query: str) -> str:
    """Convenience function returning sanitized query string."""
    return SecurityGuardrails.sanitize_user_query(query)

