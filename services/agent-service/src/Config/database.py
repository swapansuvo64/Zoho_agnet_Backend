from supabase import create_async_client, AsyncClient
from src.Config.settings import settings

supabase_client: AsyncClient = None

async def init_db() -> AsyncClient:
    global supabase_client
    try:
        supabase_client = await create_async_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )
        # Test connection by making a small select query
        await supabase_client.table("users").select("id").limit(1).execute()
        return supabase_client
    except Exception as e:
        raise RuntimeError(f"Database connection error: failed to initialize Supabase client. Details: {str(e)}") from e

async def get_db() -> AsyncClient:
    if supabase_client is None:
        raise RuntimeError("Database client has not been initialized. Please run init_db() first.")
    return supabase_client
