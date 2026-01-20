# ============================================================
# 1. CONFIGURATION
# ============================================================

# config.py
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional
import os

load_dotenv()

class Settings(BaseSettings):
    # API Keys
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")

    def model_post_init(self, __context):
        if not self.OPENAI_API_KEY and self.OPENAI_API_CANDIDATE_KEY:
            self.OPENAI_API_KEY = self.OPENAI_API_CANDIDATE_KEY
    
    # Database
    DATABASE_URL: str = "postgresql://user:pass@localhost/taxai"
    REDIS_URL: str = "redis://localhost:6379"
    
    # Storage
    S3_BUCKET: str = "taxai-documents"
    
    # External APIs
    CLEARTAX_API_KEY: Optional[str] = None
    TALLY_API_URL: Optional[str] = None
    
    class Config:
        env_file = ".env"

settings = Settings()
