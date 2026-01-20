"""
EasyScale Configuration Module

Centralized configuration for the EasyScale system.
Includes DSPy settings, Supabase connection, and environment variables.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DSPyConfig(BaseModel):
    """Configuration for DSPy language model."""

    provider: str = Field(default="openai", description="LLM provider (openai, anthropic, groq)")
    model: str = Field(default="gpt-4o-mini", description="Model identifier")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=1000, ge=1, description="Maximum tokens in response")


class SupabaseConfig(BaseModel):
    """Configuration for Supabase database connection."""

    url: str = Field(description="Supabase project URL")
    key: str = Field(description="Supabase anon/service key")
    schema: str = Field(default="public", description="Database schema")


class EasyScaleSettings(BaseSettings):
    """
    Main settings class for EasyScale.
    Loads configuration from environment variables with .env file support.
    """

    # DSPy Configuration
    dspy_provider: str = Field(default="openai", env="DSPY_PROVIDER")
    dspy_model: str = Field(default="gpt-4o-mini", env="DSPY_MODEL")
    dspy_temperature: float = Field(default=0.3, env="DSPY_TEMPERATURE")
    dspy_max_tokens: int = Field(default=1000, env="DSPY_MAX_TOKENS")

    # API Keys
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, env="GROQ_API_KEY")

    # Supabase
    supabase_url: str = Field(env="SUPABASE_URL")
    supabase_key: str = Field(env="SUPABASE_KEY")
    supabase_schema: str = Field(default="public", env="SUPABASE_SCHEMA")

    # Application Settings
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    debug_mode: bool = Field(default=False, env="DEBUG_MODE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def dspy_config(self) -> DSPyConfig:
        """Get DSPy configuration object."""
        return DSPyConfig(
            provider=self.dspy_provider,
            model=self.dspy_model,
            temperature=self.dspy_temperature,
            max_tokens=self.dspy_max_tokens,
        )

    @property
    def supabase_config(self) -> SupabaseConfig:
        """Get Supabase configuration object."""
        return SupabaseConfig(
            url=self.supabase_url,
            key=self.supabase_key,
            schema=self.supabase_schema,
        )

    def get_api_key(self) -> Optional[str]:
        """Get the appropriate API key based on DSPy provider."""
        if self.dspy_provider == "openai":
            return self.openai_api_key
        elif self.dspy_provider == "anthropic":
            return self.anthropic_api_key
        elif self.dspy_provider == "groq":
            return self.groq_api_key
        return None


# Singleton instance
_settings: Optional[EasyScaleSettings] = None


def get_settings() -> EasyScaleSettings:
    """
    Get or create the global settings instance.

    Returns:
        EasyScaleSettings singleton
    """
    global _settings
    if _settings is None:
        _settings = EasyScaleSettings()
    return _settings


def reset_settings() -> None:
    """Reset the settings singleton (useful for testing)."""
    global _settings
    _settings = None
