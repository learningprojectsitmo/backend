from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    # DATABASE_URL: str = "postgresql://postgres:password@127.0.0.1/backend_db" TODO learn postgresql
    DATABASE_URL: str = "sqlite:///test.db"

    # JWT
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    # CORS - исправленные настройки для Docker
    CORS_ORIGINS: list = [
        "http://localhost:8000",
        "http://localhost:5173",
        "http://backend:8000",
        "http://localhost",
        "http://localhost:8083",
        "http://frontend:80",
        "fpin-projects.ru",
        "http://fpin-projects.ru:1268/",
        "http://fpin-projects.ru:12683/"
    ]


    class Config:
        env_file = "../.env"
        extra = "ignore"


settings = Settings()
