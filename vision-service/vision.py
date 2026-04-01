import base64
import json
import logging

import httpx
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


def _parse_json_response(content: str) -> dict:
    """Parse JSON from model response, stripping markdown fences if present."""
    clean = content.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
    if clean.endswith("```"):
        clean = "\n".join(clean.split("\n")[:-1])
    clean = clean.strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse model response as JSON: {content[:500]}")
        return {"raw_response": content}


async def _analyze_ollama(
    client: httpx.AsyncClient,
    image_bytes: bytes,
    prompt: str,
) -> dict:
    """Send image to Ollama vision model."""
    img_b64 = base64.b64encode(image_bytes).decode()

    logger.info(f"Ollama request: model={settings.ollama_model}, image={len(image_bytes) // 1024}KB")
    resp = await client.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "user", "content": prompt, "images": [img_b64]},
            ],
        },
        timeout=300.0,
    )
    resp.raise_for_status()

    result = resp.json()
    content = result["message"]["content"]
    duration_ms = round(result.get("total_duration", 0) / 1e6)
    logger.info(f"Ollama response received in {duration_ms}ms")

    parsed = _parse_json_response(content)
    parsed["duration_ms"] = duration_ms
    parsed["provider"] = "ollama"
    return parsed


async def _analyze_openrouter(
    image_bytes: bytes,
    prompt: str,
) -> dict:
    """Send image to OpenRouter vision model (OpenAI-compatible API)."""
    img_b64 = base64.b64encode(image_bytes).decode()

    client = AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    )

    logger.info(f"OpenRouter request: model={settings.openrouter_model}, image={len(image_bytes) // 1024}KB")
    response = await client.chat.completions.create(
        model=settings.openrouter_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            },
        ],
        temperature=0.0,
    )

    content = response.choices[0].message.content or ""
    logger.info(f"OpenRouter response received (usage: {response.usage})")

    parsed = _parse_json_response(content)
    parsed["provider"] = "openrouter"
    return parsed


def _is_empty_response(parsed: dict) -> bool:
    """Check if model returned an empty or failed response."""
    if "raw_response" in parsed and not parsed["raw_response"]:
        return True
    return False


async def analyze_image(
    http_client: httpx.AsyncClient,
    image_bytes: bytes,
    prompt: str,
    max_retries: int = 2,
) -> dict:
    """Analyze image with vision model. Retries on empty response."""
    for attempt in range(1, max_retries + 1):
        if settings.vision_provider == "openrouter":
            result = await _analyze_openrouter(image_bytes, prompt)
        else:
            result = await _analyze_ollama(http_client, image_bytes, prompt)

        if not _is_empty_response(result):
            return result

        logger.warning(f"Empty response from model (attempt {attempt}/{max_retries}), retrying...")

    logger.error(f"All {max_retries} attempts returned empty response")
    return result
