import os
import dspy
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings

# Carrega .env automaticamente ao importar este módulo.
# Necessário quando rodando como -m (módulo), onde pydantic-settings
# não encontra o .env pelo caminho relativo.
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_path = Path(__file__).parent.parent.parent / ".env"
    _load_dotenv(_env_path, override=True)
except ImportError:
    pass  # python-dotenv não instalado — ok em produção via variáveis de ambiente

class SupabaseConfig(BaseModel):
    url: str = Field(description="Supabase project URL")
    key: str = Field(description="Supabase anon/service key")
    # Mudamos 'schema' para 'supabase_schema' para evitar conflito com o Pydantic
    supabase_schema: str = Field(default="public", description="Database schema")

class EasyScaleSettings(BaseSettings):
    # Configuração moderna para Pydantic V2
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # <--- ISSO RESOLVE O SEU ERRO PRINCIPAL
    )

    # DSPy Configuration
    dspy_provider: str = Field(default="openai", env="DSPY_PROVIDER")
    dspy_model: str = Field(default="gpt-4o-mini", env="DSPY_MODEL")
    dspy_temperature: float = Field(default=0.3, env="DSPY_TEMPERATURE")
    dspy_max_tokens: int = Field(default=1000, env="DSPY_MAX_TOKENS")

    # API Keys
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, env="GROQ_API_KEY")
    xai_api_key: Optional[str] = Field(default=None, env="XAI_API_KEY")
    glm_api_key: Optional[str] = Field(default=None, env="GLM_API_KEY")
    glm_model: str = Field(default="glm-4.7-flash", env="GLM_MODEL")
    glm_max_tokens: int = Field(default=300, env="GLM_MAX_TOKENS")
    glm_timeout: int = Field(default=60, env="GLM_TIMEOUT")  # seconds

    # Receptionist LLM (simulator — isolated from main SDR model)
    receptionist_model: str = Field(
        default="openai/glm-4.7-flash", env="RECEPTIONIST_MODEL"
    )
    receptionist_api_base: Optional[str] = Field(
        default="https://open.bigmodel.cn/api/paas/v4/", env="RECEPTIONIST_API_BASE"
    )
    receptionist_api_key: Optional[str] = Field(
        default=None, env="RECEPTIONIST_API_KEY"
    )

    # API Authentication
    api_key: Optional[str] = Field(default=None, env="API_KEY")

    # Supabase
    supabase_url: str = Field(default="", env="SUPABASE_URL")
    supabase_key: str = Field(default="", env="SUPABASE_KEY")
    supabase_schema: str = Field(default="public", env="SUPABASE_SCHEMA")

    def get_api_key(self) -> Optional[str]:
        if self.dspy_provider == "openai": return self.openai_api_key
        if self.dspy_provider == "anthropic": return self.anthropic_api_key
        if self.dspy_provider == "groq": return self.groq_api_key
        if self.dspy_provider == "xai": return self.xai_api_key
        if self.dspy_provider == "glm": return self.glm_api_key
        return None

_settings: Optional[EasyScaleSettings] = None

def get_settings() -> EasyScaleSettings:
    global _settings
    if _settings is None:
        _settings = EasyScaleSettings()
    return _settings

def init_dspy() -> None:
    settings = get_settings()
    api_key = settings.get_api_key()
    
    if not api_key:
        print("⚠️ Warning: No API Key found for DSPy provider.")
        return

    try:
        # Novo padrão DSPy 2.5+
        if settings.dspy_provider == "xai":
            lm = dspy.LM(
                model=f"openai/{settings.dspy_model}",
                api_key=api_key,
                api_base="https://api.x.ai/v1",
                temperature=settings.dspy_temperature,
                max_tokens=settings.dspy_max_tokens
            )
        elif settings.dspy_provider == "glm":
            lm = dspy.LM(
                model=f"openai/{settings.dspy_model}",
                api_key=api_key,
                api_base="https://open.bigmodel.cn/api/paas/v4/",
                temperature=settings.dspy_temperature,
                max_tokens=settings.dspy_max_tokens
            )
        else:
            lm = dspy.LM(
                model=f"{settings.dspy_provider}/{settings.dspy_model}",
                api_key=api_key,
                temperature=settings.dspy_temperature,
                max_tokens=settings.dspy_max_tokens
            )
        dspy.settings.configure(lm=lm)
        print(f"✅ DSPy Motor initialized with {settings.dspy_provider}/{settings.dspy_model}")
    except Exception as e:
        print(f"❌ Failed to initialize DSPy: {e}")