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

    # eGO Real Estate — CRM da agência (fonte de verdade para imóveis)
    egorealestate_api_key: str = ""
    egorealestate_base_url: str = "http://websiteapi.egorealestate.com"
    egorealestate_language: str = "PT-PT"
    egorealestate_sync_secret: str = ""  # header X-Sync-Secret, usado pelo cron (GitHub Actions)

    # eGO Real Estate — CRM backoffice autenticado (validação de disponibilidade,
    # cobre imóveis nunca publicados que a Web API pública não vê)
    egorealestate_crm_username: str = ""
    egorealestate_crm_password: str = ""
    egorealestate_crm_base_url: str = "https://admin.egorealestate.com"

    # Scraper de relatório eGO (jmarques_todas_as_colunas) — app Fly.io
    # separada e dedicada, Playwright não cabe na RAM da app principal.
    scraper_service_url: str = ""
    scraper_service_secret: str = ""

    # Automações externas (Make, n8n) — header X-Automacao-Secret.
    # Segredo próprio e não o de sync: quem ingere leads não tem de poder
    # disparar syncs do eGO, e rodar um não obriga a rodar o outro.
    automacao_secret: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Meta WhatsApp Business
    meta_whatsapp_token: str = ""       # Graph API access token
    meta_app_secret: str = ""           # Meta App Secret (para verificar assinaturas)
    meta_phone_number_id: str = ""
    meta_verify_token: str = ""
    meta_api_version: str = "v19.0"

    # Notificações ao corretor (lead qualificada, escalamento), via Microsoft
    # Graph — o correio da agência é M365 e o SMTP AUTH está a ser extinto no
    # Exchange Online. Registo de aplicação no Entra ID com permissão de
    # aplicação `Mail.Send` e consentimento de administrador.
    # Tudo vazio = notificações desligadas, sem erro: permite deployar antes de
    # haver credenciais. `notificacoes_para` aceita vários, separados por vírgula.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_remetente: str = ""        # mailbox com licença que aparece como remetente
    notificacoes_para: str = ""

    # App
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"


settings = Settings()
