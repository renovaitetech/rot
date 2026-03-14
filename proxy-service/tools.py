from typing import Any
import httpx
import logging

from config import settings

logger = logging.getLogger(__name__)

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Семантический поиск по проектной документации. Находит релевантные фрагменты документов по смысловому запросу. Используй этот инструмент когда пользователь спрашивает о содержании документов, технических требованиях, спецификациях или любой информации из проектной документации.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на любом языке, описывающий что нужно найти в документации",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество результатов (по умолчанию 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_ROUTES: dict[str, str] = {
    "search_documents": "/tools/search_documents",
}


async def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call by routing to mcp-server."""
    route = TOOL_ROUTES.get(name)
    if not route:
        return {"error": f"Unknown tool: {name}"}

    url = f"{settings.mcp_server_url}{route}"
    logger.info(f"Executing tool '{name}' -> {url}")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=args)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Tool '{name}' HTTP error: {e.response.status_code}")
        return {"error": f"MCP server error: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return {"error": f"Tool execution failed: {str(e)}"}
