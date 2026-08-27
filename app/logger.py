import logging
import json
from datetime import datetime, timezone
from app.config import settings

class SecretRedactingFormatter(logging.Formatter):
    """
    A custom JSON formatter that redacts secrets from logs.
    """
    # Key names that generally hint at secrets
    SECRETS_KEYS = ["api_key", "token", "password", "secret", "credentials"]
    
    def __init__(self):
        super().__init__()
        # Explicit values to redact from any string output
        self.exact_secrets = [
            s for s in [
                settings.nvidia_api_key,
                settings.whatsapp_access_token,
                settings.whatsapp_verify_token
            ] if s and len(s) > 2
        ]

    def _redact_string(self, text: str) -> str:
        for secret in self.exact_secrets:
            text = text.replace(secret, "***REDACTED***")
        return text

    def _redact(self, data):
        if isinstance(data, dict):
            redacted = {}
            for k, v in data.items():
                if any(secret_key in k.lower() for secret_key in self.SECRETS_KEYS):
                    redacted[k] = "***REDACTED***"
                else:
                    redacted[k] = self._redact(v)
            return redacted
        elif isinstance(data, list):
            return [self._redact(item) for item in data]
        elif isinstance(data, str):
            return self._redact_string(data)
        return data

    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Handle extra fields
        if hasattr(record, "extra"):
            extra_data = self._redact(record.extra)
            log_record.update(extra_data)
            
        # Optional: Add exception info
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        json_str = json.dumps(log_record)
        return self._redact_string(json_str)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = SecretRedactingFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Prevent log messages from propagating to the root logger and being printed multiple times
        logger.propagate = False 
    return logger
