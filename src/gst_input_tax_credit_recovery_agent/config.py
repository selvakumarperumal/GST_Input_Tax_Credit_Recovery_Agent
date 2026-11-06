from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gst_itc_recovery_agent"
