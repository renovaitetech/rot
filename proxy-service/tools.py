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
            "description": (
                "Search the project document catalog by name or category. "
                "Use ONLY when the user asks what documents exist in the project, "
                "wants a list of drawings or specifications, or asks about a specific document by name. "
                "Examples: 'what drawings do we have?', 'show me presentation files', 'list all documents'. "
                "Returns document metadata: title, category, description. "
                "Do NOT use this to find specific technical content, requirements, or data — use search_chunks instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Document name or category to search for",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category: drawing, presentation, text_spec, table_spec",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 5)",
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
            "name": "search_chunks",
            "description": (
                "Search the full text content of project documents. "
                "Use for ANY question about technical content, requirements, specifications, descriptions, or data. "
                "Examples: 'brand beskrivning enligt BBR', 'fire safety requirements', "
                "'building height specifications', 'what does the document say about X'. "
                "This searches inside documents and returns actual text passages. "
                "Use this by default whenever the user asks about content, facts, or information from documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The information or topic to search for inside document content",
                    },
                    "document_id": {
                        "type": "string",
                        "description": "Optional: restrict search to a specific document by ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default 5)",
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
    "search_chunks": "/tools/search_chunks",
}


async def execute_tool(name: str, args: dict[str, Any], client: httpx.AsyncClient) -> dict[str, Any]:
    """Execute a tool call by routing to mcp-server."""
    route = TOOL_ROUTES.get(name)
    if not route:
        return {"error": f"Unknown tool: {name}"}

    url = f"{settings.mcp_server_url}{route}"
    logger.info(f"Executing tool '{name}' -> {url}")

    try:
        resp = await client.post(url, json=args)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Tool '{name}' HTTP error: {e.response.status_code}")
        return {"error": f"MCP server error: {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return {"error": f"Tool execution failed: {str(e)}"}
