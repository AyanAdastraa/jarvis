from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ============================================================
    # NVIDIA / MODEL
    # ============================================================

    nvidia_api_key: str = Field(default="")
    nvidia_model: str = Field(
        default="nvidia/nemotron-3-ultra-550b-a55b"
    )

    # ============================================================
    # MODEL ROUTING
    # ============================================================

    fast_model: str = Field(default="nvidia/llama-3.3-nemotron-super-49b-v1")
    complex_model: str = Field(default="nvidia/nemotron-3-ultra-550b-a55b")
    model_routing_enabled: bool = Field(default=True)
    model_max_tokens: int = Field(default=1024, env="MODEL_MAX_TOKENS")

    # Agent Limits
    agent_max_iterations: int = Field(default=10, env="AGENT_MAX_ITERATIONS")
    agent_max_tool_calls: int = Field(default=20, env="AGENT_MAX_TOOL_CALLS")
    agent_max_replans: int = Field(default=3, env="AGENT_MAX_REPLANS")

    fast_model_timeout: int = Field(default=30)
    nemotron_timeout: int = Field(default=180)

    # ============================================================
    # DATABASE
    # ============================================================

    database_url: str = Field(
        default="sqlite:///workspace/jarvis.db"
    )

    # ============================================================
    # WHATSAPP
    # ============================================================

    whatsapp_access_token: str = Field(default="")
    whatsapp_phone_number_id: str = Field(default="")
    whatsapp_verify_token: str = Field(default="")
    whatsapp_api_version: str = Field(default="v21.0")
    whatsapp_enabled: bool = Field(default=False)
    whatsapp_mock_mode: bool = Field(default=True)
    whatsapp_max_message_length: int = Field(default=4096)
    whatsapp_rate_limit_per_minute: int = Field(default=30)

    # ============================================================
    # CONTEXT
    # ============================================================

    max_context_tokens: int = 4000

    # ============================================================
    # FILESYSTEM / WORKSPACE
    # ============================================================

    max_file_read_size: int = 100 * 1024  # 100 KB
    max_search_results: int = 50

    # ============================================================
    # TERMINAL
    # ============================================================

    command_timeout: int = 30  # seconds
    max_command_output_size: int = 100 * 1024  # 100 KB

    # IMPORTANT:
    # Do not add pip/ls/grep/find here.
    # Filesystem operations are handled by JARVIS filesystem tools.
    terminal_allowlist: list[str] = [
        "python",
        "pytest",
        "ruff",
        "git",
        "node",
        "npm",
    ]

    # ============================================================
    # PYDANTIC SETTINGS
    # ============================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ============================================================
    # SECRET REDACTION
    # ============================================================

    def _redact_dict(self) -> dict:
        data = self.model_dump()

        secret_keywords = (
            "api_key",
            "token",
            "password",
            "secret",
            "credential",
            "private_key",
        )

        for key, value in data.items():
            key_lower = key.lower()

            if any(keyword in key_lower for keyword in secret_keywords):
                if value:
                    data[key] = "***REDACTED***"

        return data

    def __str__(self) -> str:
        return str(self._redact_dict())

    def __repr__(self) -> str:
        return f"Settings({self._redact_dict()})"


settings = Settings()