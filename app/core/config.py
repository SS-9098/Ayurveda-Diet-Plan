# Environment variables (DB_URI, JWT_SECRET)
from pydantic import BaseSettings

class Settings(BaseSettings):
    MONGO_URI: str
    AYUSHMITRA: str

    class Config:
        env_file = ".env"

settings = Settings()
