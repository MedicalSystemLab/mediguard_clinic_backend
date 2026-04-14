from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import quote_plus

# 프로젝트 루트 디렉토리를 찾습니다 (.env 파일이 있는 곳)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env_path = BASE_DIR / ".env"

# .env 파일을 명시적으로 로드합니다.
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # 현재 작업 디렉토리에서 기본적으로 로드

class Settings(BaseSettings):
    PROJECT_NAME: str = "mediguard-clinic-backend"
    API_STR: str = "/api"
    API_V1_STR: str = "/v1"
    
    # Database Configuration
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", 5432))
    
    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC_BIOSIGNAL: str = "biosignal-events"
    KAFKA_TOPIC_AUTH: str = "auth-events"
    KAFKA_TOPIC_USER: str = "clinical_manage-events"
    
    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD")
    
    # Security & JWT Configuration
    # Generate a secret key: openssl rand -hex 32
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = "HS256"
    JWT_ISSUER: str = os.getenv("JWT_ISSUER", "mediguard-clinic-auth")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    REFRESH_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", 10080))
    
    # Data Encryption & Hashing
    # AES-256 key (32 bytes Base64): openssl rand -base64 32
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY")
    # Fixed salt for deterministic hashing (Base64): openssl rand -base64 32
    EMAIL_HASH_SALT: str = os.getenv("EMAIL_HASH_SALT")
    TIMEZONE: str = "UTC"
    
    @property
    def DATABASE_URL(self) -> str:
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{encoded_password}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        case_sensitive=True, 
        env_file=str(env_path) if env_path.exists() else ".env",
        extra="ignore"
    )

try:
    settings = Settings()
except Exception as e:
    import sys
    print("\n[ERROR] Configuration failed to load.")
    print(f"[REASON] {e}")
    print("\nPlease check your '.env' file. You can use '.env.example' as a template.")
    print("Required keys (SECRET_KEY, ENCRYPTION_KEY, EMAIL_HASH_SALT) must be set.\n")
    sys.exit(1)
