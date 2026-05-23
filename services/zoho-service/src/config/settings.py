from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    ZOHO_BASE_URL: str = "https://projectsapi.zoho.in/restapi"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
