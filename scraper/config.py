import os

from dotenv import load_dotenv

load_dotenv()

egorealestate_crm_username = os.environ.get("EGOREALESTATE_CRM_USERNAME", "")
egorealestate_crm_password = os.environ.get("EGOREALESTATE_CRM_PASSWORD", "")
egorealestate_crm_base_url = os.environ.get("EGOREALESTATE_CRM_BASE_URL", "https://admin.egorealestate.com")

supabase_imoveis_url = os.environ.get("SUPABASE_IMOVEIS_URL", "")
supabase_imoveis_key = os.environ.get("SUPABASE_IMOVEIS_KEY", "")

scraper_service_secret = os.environ.get("SCRAPER_SERVICE_SECRET", "")
