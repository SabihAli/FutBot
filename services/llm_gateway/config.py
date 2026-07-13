import os


class Settings:
    def __init__(self) -> None:
        self.llm_provider = os.getenv("LLM_PROVIDER", "local").lower()
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_max_retries = int(os.getenv("GROQ_MAX_RETRIES", "5"))
        self.groq_backoff_base = float(os.getenv("GROQ_BACKOFF_BASE", "1.5"))
        self.snapshot_max_tokens = int(os.getenv("SNAPSHOT_MAX_TOKENS", "300"))
        self.llm_rate_limit_rpm = int(os.getenv("LLM_RATE_LIMIT_RPM", "60"))
        self.model_orchestrator = os.getenv("MODEL_ORCHESTRATOR", "Qwen/Qwen3.5-0.8B")
        self.model_generator = os.getenv("MODEL_GENERATOR", "Qwen/Qwen3.5-2B")
        self.model_decision = os.getenv("MODEL_DECISION", "Qwen/Qwen3.5-4B")
        self.url_08b = os.getenv(
            "URL_08B",
            "https://3ed4-2407-d000-2b-3df3-26d-b720-e3f1-5827.ngrok-free.app/v1/chat/completions",
        )
        self.url_2b = os.getenv(
            "URL_2B",
            "https://6006-154-192-5-123.ngrok-free.app/v1/chat/completions",
        )
        self.url_4b = os.getenv(
            "URL_4B",
            "https://19d9-154-192-5-123.ngrok-free.app/v1/chat/completions",
        )
        self.groq_model_main = os.getenv("GROQ_MODEL_MAIN", "qwen/qwen3.6-27b")
        self.groq_model_orchestrator = os.getenv(
            "GROQ_MODEL_ORCHESTRATOR", "openai/gpt-oss-20b"
        )


settings = Settings()
