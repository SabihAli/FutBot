# ADR-008: Tools & MCP Service (Phase 7)

**Status:** Accepted  
**Date:** 2026-07-15

## Decisions

| Topic | Decision |
|-------|----------|
| Web search | Tavily primary, Serper fallback; **opt-in** via `web_search_enabled` on chat message |
| Football MCP | LiveScore (SSE) + API-Football (stdio); implicitly available when configured |
| PDF export | md-pdf-mcp primary, md-to-pdf-mcp fallback; Chat `export?format=pdf` |
| TOOL path | `tool_planner → tool_executor` **parallel** with `retriever` → single `drafter` |
| HYBRID | Removed — retrieval always runs on TOOL path |
| Web search skipped | Planner may include `web_search`; executor skips if disabled; `tool_notice` in response |
| MCP down | Downgrade TOOL → KNOWLEDGE + `MCP_UNAVAILABLE` notice |
| Gateway | `GET /tools` proxied; `POST /tools/execute` internal (501 on gateway) |
| Models | 120b compressor+drafter; 32b rewriter+simple; 27b planner+judge+vision; 20b orchestrator+classifier |

## Flow

```
POST /chats/{id}/messages { web_search_enabled }
  → POST /pipeline/run
  → TOOL: parallel(tools, retrieve) → drafter → judge
  → tool_notice when web_search planned but skipped
```
