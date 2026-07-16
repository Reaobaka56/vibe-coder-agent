"""
Secrets Management and Audit Utilities

This module provides utilities to ensure sensitive credentials are never:
1. Logged or printed
2. Committed to version control
3. Exposed in error messages
"""

import logging
import re
from app.config import config

logger = logging.getLogger("secrets_audit")

# Sensitive patterns to prevent from leaking
SENSITIVE_PATTERNS = {
    "github_private_key": r"-----BEGIN RSA PRIVATE KEY-----",
    "github_app_secret": r"[a-f0-9]{40}",  # GitHub App secret pattern
    "twilio_token": r"auth.*token",
    "api_key": r"api[_-]?key",
    "dashscope_key": r"sk[_-]",  # DashScope API key pattern
}

# Redaction character for logs
REDACTION = "***REDACTED***"


def redact_sensitive_data(text: str) -> str:
    """
    Redact sensitive data from text for safe logging.
    
    Args:
        text: The text to redact
        
    Returns:
        Text with sensitive values replaced with REDACTION marker
    """
    result = text
    
    # Redact private keys
    if config.GITHUB_PRIVATE_KEY:
        if config.GITHUB_PRIVATE_KEY in result:
            result = result.replace(config.GITHUB_PRIVATE_KEY, REDACTION)
        # Also redact key patterns
        result = re.sub(r'-----BEGIN.*?-----END RSA PRIVATE KEY-----', REDACTION, result, flags=re.DOTALL)
    
    # Redact tokens
    if config.TWILIO_TOKEN:
        if config.TWILIO_TOKEN in result:
            result = result.replace(config.TWILIO_TOKEN, REDACTION)
    
    if config.QWEN_API_KEY:
        if config.QWEN_API_KEY in result:
            result = result.replace(config.QWEN_API_KEY, REDACTION)
    
    if config.VERCEL_TOKEN:
        if config.VERCEL_TOKEN in result:
            result = result.replace(config.VERCEL_TOKEN, REDACTION)
    
    if config.GITHUB_CLIENT_SECRET:
        if config.GITHUB_CLIENT_SECRET in result:
            result = result.replace(config.GITHUB_CLIENT_SECRET, REDACTION)
    
    if config.GITHUB_WEBHOOK_SECRET:
        if config.GITHUB_WEBHOOK_SECRET in result:
            result = result.replace(config.GITHUB_WEBHOOK_SECRET, REDACTION)
    
    # Generic redaction for common patterns
    # Redact "token": "..." patterns
    result = re.sub(r'(["\']?(?:access_token|auth_token|secret)["\']?\s*[:=]\s*)["\']([^"\']+)["\']', 
                   r'\1"' + REDACTION + '"', result, flags=re.IGNORECASE)
    
    # Redact API key patterns
    result = re.sub(r'(["\']?(?:api_key|apikey|x-api-key)["\']?\s*[:=]\s*)["\']([^"\']+)["\']',
                   r'\1"' + REDACTION + '"', result, flags=re.IGNORECASE)
    
    return result


def log_safely(message: str, level: str = "info"):
    """
    Log a message with automatic secret redaction.
    
    Args:
        message: The message to log
        level: The logging level (info, warning, error, debug)
    """
    safe_message = redact_sensitive_data(message)
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(safe_message)


def audit_secrets_exposure():
    """
    Audit for common secrets exposure patterns.
    Call this during startup to warn about potential leaks.
    
    Returns:
        List of warnings if any issues found
    """
    warnings = []
    
    # Check if private key is set and not empty
    if not config.GITHUB_PRIVATE_KEY:
        warnings.append("⚠️ GITHUB_PRIVATE_KEY not set - GitHub operations will fail")
    elif "-----BEGIN" not in config.GITHUB_PRIVATE_KEY:
        warnings.append("⚠️ GITHUB_PRIVATE_KEY looks malformed - check PEM format")
    
    # Check if tokens are empty (not ideal but not a leak)
    if not config.TWILIO_TOKEN:
        warnings.append("⚠️ TWILIO_TOKEN not set - WhatsApp will not work")
    
    if not config.QWEN_API_KEY and "localhost" not in config.QWEN_API_URL.lower():
        warnings.append("⚠️ QWEN_API_KEY not set but using remote API - requests will fail")
    
    if not config.VERCEL_TOKEN:
        warnings.append("⚠️ VERCEL_TOKEN not set - deployments will fail")
    
    # Log warnings
    for warning in warnings:
        logger.warning(f"[SECRETS_AUDIT] {warning}")
    
    return warnings


class SecretsSafeFormatter(logging.Formatter):
    """
    Custom logging formatter that redacts secrets from all log messages.
    Use this to ensure no secrets leak into logs regardless of where logging happens.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # First, format the message normally
        result = super().format(record)
        # Then redact any secrets
        result = redact_sensitive_data(result)
        return result
