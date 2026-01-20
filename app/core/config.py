import dspy
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings

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

    # Supabase
    supabase_url: str = Field(default="", env="SUPABASE_URL")
    supabase_key: str = Field(default="", env="SUPABASE_KEY")
    supabase_schema: str = Field(default="public", env="SUPABASE_SCHEMA")

    def get_api_key(self) -> Optional[str]:
        if self.dspy_provider == "openai": return self.openai_api_key
        if self.dspy_provider == "anthropic": return self.anthropic_api_key
        if self.dspy_provider == "groq": return self.groq_api_key
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
        # Usando dspy.OpenAI para compatibilidade
        lm = dspy.OpenAI(
            model=settings.dspy_model, 
            api_key=api_key, 
            temperature=settings.dspy_temperature,
            max_tokens=settings.dspy_max_tokens
        )
        dspy.settings.configure(lm=lm)
    except Exception as e:
        print(f"❌ Failed to initialize DSPy: {e}")