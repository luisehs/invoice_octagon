# app/db/supabase_client.py
from supabase import create_client, Client
from app.core.config import settings

print(f"Conectando a Supabase... {settings.SUPABASE_URL} (key: ****{settings.SUPABASE_KEY[-4:]})")

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

try:
    resp = supabase.table("users").select("u_id").limit(1).execute()
    print(f"Supabase OK: status={getattr(resp, 'status_code', '?')}, rows={len(resp.data) if resp.data else 0}")
except Exception as e:
    print(f"Supabase conexión falló: {e}")
