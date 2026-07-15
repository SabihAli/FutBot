import logging

from services.tools.config import settings
from services.tools.mcp.bridge import call_sse_tool, make_mcp_tool_handler
from services.tools.registry import MARKDOWN_TO_PDF_TOOL, register_tool, set_mcp_healthy
from services.tools.schemas import ToolDefinition

logger = logging.getLogger(__name__)

LIVESCORE_TOOLS = [
    ("get_live_scores", "Currently live matches with scores"),
    ("get_fixtures", "Competition fixtures"),
    ("search", "Search teams, players, or competitions"),
    ("get_league_fixtures", "League-specific fixtures"),
    ("get_team", "Team info, squad, statistics"),
    ("get_player", "Player profile and stats"),
    ("get_match", "Full match details"),
    ("get_day_fixtures", "All matches for a specific date"),
    ("get_team_image", "Team logo PNG URL"),
    ("health", "MCP connectivity check"),
]

API_FOOTBALL_TOOLS = [
    ("get_standings", "Premier League standings"),
    ("get_fixtures", "Match fixtures"),
    ("get_team", "Team information"),
    ("get_player", "Player profile"),
    ("get_match_goals", "Goal events for a match"),
    ("get_match_events", "All match events"),
    ("get_squad", "Team squad for a season"),
    ("search_teams", "Search teams by name"),
    ("search_players", "Search players"),
    ("get_live_matches", "Currently live matches"),
    ("get_rate_limit", "API rate-limit status"),
]


def _livescore_caller(mcp_tool: str, arguments: dict) -> dict:
    return call_sse_tool(settings.livescore_mcp_url, mcp_tool, arguments)


def _api_football_caller(mcp_tool: str, arguments: dict) -> dict:
    from services.tools.mcp.bridge import call_stdio_tool

    env = {"API_FOOTBALL_KEY": settings.api_football_key}
    return call_stdio_tool(
        settings.api_football_mcp_command,
        settings.api_football_mcp_args,
        env,
        mcp_tool,
        arguments,
    )


class MarkdownToPdfTool:
    name = MARKDOWN_TO_PDF_TOOL

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Convert markdown to PDF (export only).",
            source="mcp",
        )

    def execute(self, arguments: dict) -> dict:
        import base64

        from services.tools.mcp.bridge import markdown_to_pdf

        markdown = str(arguments.get("markdown", ""))
        title = str(arguments.get("title", "Chat Export"))
        if not markdown.strip():
            raise ValueError("markdown is required")
        pdf_bytes = markdown_to_pdf(markdown, title=title)
        return {
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "size_bytes": len(pdf_bytes),
        }


def register_pdf_tool() -> None:
    register_tool(MarkdownToPdfTool())


def register_football_mcp_tools() -> None:
    if settings.livescore_mcp_enabled:
        for tool_name, desc in LIVESCORE_TOOLS:
            make_mcp_tool_handler(
                name=f"mcp:livescore:{tool_name}",
                description=desc,
                mcp_tool=tool_name,
                caller=_livescore_caller,
            )

    if settings.api_football_mcp_enabled and settings.api_football_key:
        for tool_name, desc in API_FOOTBALL_TOOLS:
            make_mcp_tool_handler(
                name=f"mcp:api-football:{tool_name}",
                description=desc,
                mcp_tool=tool_name,
                caller=_api_football_caller,
            )
