import os

from dotenv import load_dotenv

load_dotenv()

egorealestate_crm_username = os.environ.get("EGOREALESTATE_CRM_USERNAME", "")
egorealestate_crm_password = os.environ.get("EGOREALESTATE_CRM_PASSWORD", "")
egorealestate_crm_base_url = os.environ.get("EGOREALESTATE_CRM_BASE_URL", "https://admin.egorealestate.com")

# Projecto único desde 13/09 (o de Auth foi eliminado e integrado neste) --
# chave nova (sb_secret_...), ver docs/fases/migracao-supabase-chaves-novas-plano.md
# no repo principal.
supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_secret_key = os.environ.get("SUPABASE_SECRET_KEY", "")

scraper_service_secret = os.environ.get("SCRAPER_SERVICE_SECRET", "")
