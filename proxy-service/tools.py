from typing import Any

# Список tools, передаваемых в DeepSeek.
# Формат: OpenAI function calling schema.
# Заглушка — заполнить при реализации конкретных инструментов.
TOOLS: list[dict[str, Any]] = []


async def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Выполнить tool call по имени функции."""
    return {"error": f"tool '{name}' not implemented"}
