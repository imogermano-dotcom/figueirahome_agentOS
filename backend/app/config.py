from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Anthropic
    anthropic_api_key: str = ""

    # Telnyx
    telnyx_api_key: str = ""
    telnyx_public_key: str = ""
    telnyx_phone_number: str = ""

    # Supabase — projecto principal
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Supabase — projecto imóveis (segunda base)
    supabase_imoveis_url: str = ""
    supabase_imoveis_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Meta WhatsApp Business
    meta_whatsapp_token: str = ""       # Graph API access token
    meta_app_secret: str = ""           # Meta App Secret (para verificar assinaturas)
    meta_phone_number_id: str = ""
    meta_verify_token: str = ""
    meta_api_version: str = "v19.0"

    # App
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"


settings = Settings()
