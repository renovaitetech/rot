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
            "description": "Поиск тендерной документации по запросу. Возвращает список тендеров с названием, статусом, дедлайном и бюджетом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос, например 'кровля', 'коммуникации', 'open'",
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
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": "Получить информацию о проекте реновации по названию или адресу. Возвращает стадию, подрядчика, сроки и бюджет.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Название проекта или адрес, например 'Ленина 42', 'Мира 17'",
                    },
                },
                "required": ["project_name"],
            },
        },
    },
]

TOOL_ROUTES: dict[str, str] = {
    "search_documents": "/tools/search_documents",
    "get_project_info": "/tools/get_project_info",
}


async def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool call by routing to mcp-server."""
    route = TOOL_ROUTES.get(name)
    if not route:
        return {"error": f"Unknown tool: {name}"}

    url = f"{settings.mcp_server_url}{route}"
    logger.info(f"Executing tool '{name}' -> {url}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=args)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Tool '{name}' HTTP error: {e.response.status_code}")
        return {"error": f"MCP server error: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return {"error": f"Tool execution failed: {str(e)}"}
