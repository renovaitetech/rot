import base64
import json
import logging
import time

import httpx
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Look at this first page of a PDF document from a Swedish construction project.
Determine the document type based on its visual appearance.

Return a JSON object with these fields:

- category: one of:
  - "drawing" — architectural/engineering drawing, blueprint, floor plan, elevation, detail
  - "text_spec" — text-heavy specification, description, contract, protocol (AF, rambeskrivning, PM, etc.)
  - "presentation" — slide/presentation with graphics, photos, diagrams, colored backgrounds
  - "table_spec" — document dominated by tables, schedules, quantity lists (mängdförteckning)
- confidence: high / medium / low
- visual_cues: array of 3-5 visual features that led to your classification
  (e.g. "title block stamp", "dense paragraph text", "slide layout with logo", "dimension lines")
- title: document title if visible on this page
- description: 1-2 sentences in Swedish describing what this document appears to be

Return ONLY valid JSON, no markdown formatting, no code blocks."""


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
        return {"category": "unknown", "confidence": "low", "raw_response": content}


async def _classify_ollama(client: httpx.AsyncClient, image_bytes: bytes) -> dict:
    """Send image to Ollama vision model."""
    img_b64 = base64.b64encode(image_bytes).decode()

    logger.info(f"Ollama request: model={settings.ollama_model}, image={len(image_bytes) // 1024}KB")
    resp = await client.post(
        f"{settings.ollama_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "user", "content": CLASSIFY_PROMPT, "images": [img_b64]},
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


async def _classify_openrouter(image_bytes: bytes) -> dict:
    """Send image to OpenRouter vision model (OpenAI-compatible API)."""
    img_b64 = base64.b64encode(image_bytes).decode()

    client = AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    )

    logger.info(f"OpenRouter request: model={settings.openrouter_model}, image={len(image_bytes) // 1024}KB")
    t0 = time.monotonic()
    response = await client.chat.completions.create(
        model=settings.openrouter_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CLASSIFY_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            },
        ],
        temperature=0.0,
    )
    duration_ms = round((time.monotonic() - t0) * 1000)

    content = response.choices[0].message.content or ""
    logger.info(f"OpenRouter response received in {duration_ms}ms (usage: {response.usage})")

    parsed = _parse_json_response(content)
    parsed["duration_ms"] = duration_ms
    parsed["provider"] = "openrouter"
    return parsed


async def classify_image(client: httpx.AsyncClient, image_bytes: bytes) -> dict:
    """Classify image using the configured inference provider."""
    if settings.inference_provider == "openrouter":
        return await _classify_openrouter(image_bytes)
    return await _classify_ollama(client, image_bytes)
