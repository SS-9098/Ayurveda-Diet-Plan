# Environment variables (DB_URI, JWT_SECRET)
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGO_URI: str
    AYUSHMITRA: str
    GROQ1: str
    GROQ2: str
    GROQ3: str
    DB_NAME: str
    INGREDIENTS: str
    RECIPES: str
    ACCOUNTS: str

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()