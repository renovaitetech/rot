import base64
import json
import logging

import httpx

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


async def classify_image(
    client: httpx.AsyncClient,
    image_bytes: bytes,
    ollama_url: str,
    model: str,
) -> dict:
    """Send image to Ollama vision model and parse classification result."""
    img_b64 = base64.b64encode(image_bytes).decode()

    logger.info(f"Sending image to {model} ({len(image_bytes) // 1024}KB)")
    resp = await client.post(
        f"{ollama_url}/api/chat",
        json={
            "model": model,
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
    logger.info(f"Model response received in {duration_ms}ms")

    # Strip markdown code fences if present
    clean = content.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
    if clean.endswith("```"):
        clean = "\n".join(clean.split("\n")[:-1])

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse model response as JSON: {content}")
        parsed = {"category": "unknown", "confidence": "low", "raw_response": content}

    parsed["duration_ms"] = duration_ms
    return parsed
