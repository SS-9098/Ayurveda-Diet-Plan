# Environment variables (DB_URI, JWT_SECRET)
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGO_URI: str
    AYUSHMITRA: str
    INGREDIENTS: str
    RECIPES: str
    ACCOUNTS: str

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()