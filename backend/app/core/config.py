from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_TIMEZONE: str = "Asia/Karachi"
    # Shared by FastAPI and the n8n workflow. Leave empty only for local
    # development; production requests should always be signed.
    N8N_WEBHOOK_SECRET: str = ""
    GOOGLE_AUTH_CLIENT_ID: str = ""
    GOOGLE_AUTH_REQUIRE_VERIFIED_EMAIL: bool = True
    CHRONO_JWT_SECRET: str = ""
    CHRONO_JWT_ALGORITHM: str = "HS256"
    CHRONO_ACCESS_TOKEN_MINUTES: int = 60
    ALLOW_LEGACY_DEFAULT_USER: bool = False
    CHRONO_N8N_OWNER_USER_ID: str = ""
    FRONTEND_ORIGINS: str = ""
    MAX_INGEST_FILE_BYTES: int = 25 * 1024 * 1024
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-5.4-mini"
    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = ""
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GEMINI_EMBEDDING_DIMENSIONS: int = 1536
    GEMINI_EMBEDDING_INPUT_TOKEN_LIMIT: int = 2048
    GEMINI_EMBEDDING_BATCH_TOKEN_LIMIT: int = 18000
    GEMINI_EMBEDDING_BATCH_SIZE: int = 20
    GEMINI_TIMEOUT_SECONDS: int = 30
    GEMINI_MAX_ATTEMPTS: int = 3
    CHUNK_SIZE_TOKENS: int = 700
    CHUNK_OVERLAP_TOKENS: int = 100
    RAG_TOP_K: int = 8
    SEMANTIC_MIN_SIMILARITY: float = 0.35
    LEXICAL_MIN_RANK: float = 0.01

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
