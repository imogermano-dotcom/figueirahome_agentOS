from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Anthropic
    anthropic_api_key: str = ""

    # Telnyx
    telnyx_api_key: str = ""
    telnyx_public_key: str = ""
    telnyx_phone_number: str = ""
    # STT da voz: whisper-1 percebia mal números e nomes em áudio de telefone (17/10); gpt-4o-transcribe é bem melhor.
    stt_model: str = "gpt-4o-transcribe"
    # Modelos a comparar com o `stt_model` (separados por vírgula): correm em segundo plano e só escrevem o texto
    # nos logs, sem custo de latência na chamada. Vazio = desligado.
    stt_comparar: str = ""
    # Barge-in: se a pessoa fala por cima da assistente, o TTS pára. Desligado por omissão até se testar à parte.
    voz_barge_in: bool = False
    voz_tts: str = "Polly.Ines-Neural"  # voz do `speak` da Telnyx, ex. Azure.pt-PT-RaquelNeural

    # Supabase — projecto único (o de Auth, `fykbo...`, foi eliminado a
    # 13/09 e integrado neste — ver docs/fases/migracao-supabase-chaves-novas-plano.md).
    # Chave nova (`sb_secret_...`): as antigas anon/service_role foram
    # desactivadas pelo Supabase a nível de projecto em 12/09.
    supabase_url: str = ""
    supabase_secret_key: str = ""

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
    egorealestate_crm_office: str = "FIGUEIRAHOME"  # escritório a escolher quando a conta tem mais de um cliente

    # API do eGO (api.egocrm.com) — mesmas credenciais do CRM; escritório escolhido por nome (`egorealestate_crm_office`).
    egoapi_base_url: str = "https://api.egocrm.com"
    # Leads de compra da Meta sem resposta ao WhatsApp → eGO (`docs/fases/lead-compra-para-ego-plano.md`).
    # Data ISO a partir da qual as leads entram. Vazio = desligado: nunca envia, nem o histórico.
    lead_compra_ego_desde: str = ""

    # Scraper de relatório eGO (jmarques_todas_as_colunas) — app Fly.io
    # separada e dedicada, Playwright não cabe na RAM da app principal.
    scraper_service_url: str = ""
    scraper_service_secret: str = ""

    # Automações externas (Make, n8n) — header X-Automacao-Secret.
    # Segredo próprio e não o de sync: quem ingere leads não tem de poder
    # disparar syncs do eGO, e rodar um não obriga a rodar o outro.
    automacao_secret: str = ""
    n8n_secret: str = ""  # header X-N8N-Secret: só abre os endpoints que o n8n chama (`require_n8n_access`)

    # UptimeRobot — chave read-only, só getMonitors. O nosso próprio cron de
    # uptime foi desactivado 23/09 (redundante, o utilizador já tinha isto).
    uptimerobot_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Meta WhatsApp Business
    meta_whatsapp_token: str = ""       # Graph API access token
    meta_app_secret: str = ""           # Meta App Secret (para verificar assinaturas)
    meta_phone_number_id: str = ""
    meta_verify_token: str = ""
    meta_api_version: str = "v19.0"

    # Notificações ao corretor (lead qualificada, escalamento), via Resend
    # (REVISTO 2026-08-31 — trocou o Microsoft Graph, ver docs/decisoes.md).
    # Tudo vazio = notificações desligadas, sem erro: permite deployar antes de
    # haver credenciais. `notificacoes_para` aceita vários, separados por vírgula.
    resend_api_key: str = ""
    resend_remetente: str = ""       # remetente verificado no domínio Resend
    notificacoes_para: str = ""
    # Quem recebe, além de `notificacoes_para`, os avisos de FALHA do sistema (syncs do eGO). Vazio = só os
    # destinatários normais. Segredo no Fly, nunca no repo (público).
    alertas_para: str = ""

    # Chat do site (figueirahome.pt) -- chave partilhada com o Worker que faz
    # proxy do widget (header X-Widget-Key). Vazio = nenhum pedido passa
    # (ver require_widget_key em api/deps.py) -- ao contrário do Resend, aqui
    # "sem configurar" nunca pode significar "endpoint público aberto".
    widget_chat_secret: str = ""

    # App
    app_base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"


settings = Settings()
