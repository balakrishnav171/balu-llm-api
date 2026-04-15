"""
Application configuration using Pydantic BaseSettings.
Reads values from environment variables or .env file.
"""
from __future__ import annotations

import json
from typing import List, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -----------------------------------------------------------------
    # LLM backend selection
    # -----------------------------------------------------------------
    LLM_BACKEND: Literal["ollama", "azure_openai"] = Field(
        default="ollama",
        description="Which LLM backend to use: 'ollama' or 'azure_openai'",
    )

    # -----------------------------------------------------------------
    # Ollama settings
    # -----------------------------------------------------------------
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Base URL for the local Ollama server",
    )
    OLLAMA_MODEL: str = Field(
        default="orca-mini",
        description="Ollama model name to use",
    )

    # -----------------------------------------------------------------
    # Azure OpenAI settings
    # -----------------------------------------------------------------
    AZURE_OPENAI_ENDPOINT: Optional[str] = Field(
        default=None,
        description="Azure OpenAI resource endpoint, e.g. https://<name>.openai.azure.com/",
    )
    AZURE_OPENAI_KEY: Optional[str] = Field(
        default=None,
        description="Azure OpenAI API key",
    )
    AZURE_OPENAI_DEPLOYMENT: str = Field(
        default="gpt-4o",
        description="Azure OpenAI deployment name",
    )
    AZURE_OPENAI_API_VERSION: str = Field(
        default="2024-02-01",
        description="Azure OpenAI API version",
    )

    # -----------------------------------------------------------------
    # Auth
    # -----------------------------------------------------------------
    API_KEY: str = Field(
        default="your-secret-api-key-here",
        description="Secret key callers must supply via X-API-Key header",
    )

    # -----------------------------------------------------------------
    # Generation parameters
    # -----------------------------------------------------------------
    MAX_TOKENS: int = Field(default=1024, ge=1, le=32768)
    TEMPERATURE: float = Field(default=0.7, ge=0.0, le=2.0)

    # -----------------------------------------------------------------
    # CORS
    # -----------------------------------------------------------------
    CORS_ORIGINS: List[str] = Field(
        default=["*"],
        description='JSON list of allowed origins, e.g. ["https://example.com"]',
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> List[str]:
        """Accept either a JSON string or a real list."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                # Treat as a single comma-separated string
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v  # type: ignore[return-value]

    # -----------------------------------------------------------------
    # Application metadata
    # -----------------------------------------------------------------
    APP_TITLE: str = "Balu LLM API"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = (
        "Production-grade LLM API supporting Ollama (local) and Azure OpenAI."
    )

    # -----------------------------------------------------------------
    # Server
    # -----------------------------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"


# Singleton instance used throughout the application
settings = Settings()
