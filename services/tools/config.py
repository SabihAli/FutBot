import os


class Settings:
    def __init__(self) -> None:
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.serper_api_key = os.getenv("SERPER_API_KEY", "")
        self.request_timeout_sec = float(os.getenv("TOOLS_REQUEST_TIMEOUT_SEC", "30"))
        self.livescore_mcp_url = os.getenv(
            "LIVESCORE_MCP_URL", "https://livescoremcp.com/sse"
        )
        self.livescore_mcp_enabled = os.getenv("LIVESCORE_MCP_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.api_football_mcp_enabled = os.getenv(
            "API_FOOTBALL_MCP_ENABLED", "true"
        ).lower() in {"1", "true", "yes"}
        self.api_football_key = os.getenv("API_FOOTBALL_KEY", "")
        self.api_football_mcp_command = os.getenv(
            "API_FOOTBALL_MCP_COMMAND", "node"
        )
        self.api_football_mcp_args = os.getenv(
            "API_FOOTBALL_MCP_ARGS",
            "packages/api-football-mcp/dist/index.js",
        ).split()
        self.pdf_mcp_primary = os.getenv("PDF_MCP_PRIMARY", "md-pdf-mcp")
        self.pdf_mcp_fallback = os.getenv("PDF_MCP_FALLBACK", "md-to-pdf-mcp")


settings = Settings()
