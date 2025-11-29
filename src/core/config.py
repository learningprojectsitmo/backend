from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    # DATABASE_URL: str = "postgresql://postgres:password@127.0.0.1/backend_db" TODO learn postgresql
    DATABASE_URL: str = "sqlite:///test.db"

    # JWT
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: list = ["http://localhost:8080","http://127.0.0.1:8080","http://localhost:8080","http://127.0.0.1:8080"]

    class Config:
        env_file = "../.env"
        extra = "ignore"


settings = Settings()
