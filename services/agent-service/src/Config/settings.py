from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Zoho OAuth configurations
    ZOHO_CLIENT_ID: str
    ZOHO_CLIENT_SECRET: str
    ZOHO_REDIRECT_URI: str
    ZOHO_AUTH_URL: str
    ZOHO_TOKEN_URL: str
    ZOHO_USER_INFO_URL: str
    ZOHO_PORTALS_URL: str

    # Supabase configurations
    SUPABASE_URL: str
    SUPABASE_KEY: str

    # Redis configurations
    REDIS_URL: str

    # ChromaDB configurations
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8010

    # Cryptography
    ENCRYPTION_KEY: str

    # JWT configurations
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE: int
    JWT_REFRESH_EXPIRE: int

    # Application settings
    FRONTEND_URL: str
    ENVIRONMENT: str = "development"

    # Groq API
    GROQ_API_KEY: str
    MODEL: str
    FALL_BACK_MODEL: str

    # Google Embedding API
    GOOGLE_API_KEY: str

settings = Settings()


