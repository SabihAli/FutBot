import os


class Settings:
    def __init__(self) -> None:
        self.retrieval_service_url = os.getenv(
            "RETRIEVAL_SERVICE_URL", "http://localhost:8085"
        )
        self.hot_context_window = int(os.getenv("HOT_CONTEXT_WINDOW", "10"))


settings = Settings()
