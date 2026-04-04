# Classifier Service

Document classification service. Classifies PDF documents by category using a vision model and generates page screenshots.

**Port:** 8008

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_SERVICE_URL` | `http://storage-service:8002` | Storage service URL |
| `QDRANT_SERVICE_URL` | `http://qdrant-service:8006` | Qdrant service URL |
| `EMBEDDING_SERVICE_URL` | `http://embedding-service:8005` | Embedding service URL |
| `INFERENCE_PROVIDER` | `ollama` | Inference provider: `ollama` or `openrouter` |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama vision model name |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `OPENROUTER_MODEL` | `qwen/qwen3.5-9b` | OpenRouter model ID |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `TARGET_LONG_SIDE` | `2048` | Screenshot long side in pixels |

## Endpoints

### Classify document

```
POST /classify
```

Downloads PDF from storage, renders first page as 2K screenshot, sends it to a vision model for classification, generates thumbnails for all pages. Screenshot and thumbnails are uploaded to storage. The document is registered in the Qdrant catalog with an embedding of `title + description` (in Swedish).

- Screenshot is saved to `screenshots/{filename}.png`
- Thumbnails are saved to `thumbnails/{filename}/{filename}_page_{N}.png`

**Document categories:**
- `drawing` — architectural/engineering drawing, blueprint, floor plan
- `text_spec` — text-heavy specification, description, contract, protocol
- `presentation` — slide/presentation with graphics, photos, diagrams
- `table_spec` — document dominated by tables, schedules, quantity lists

**Request:**

```json
{
  "document_key": "raw/document.pdf",
  "project_id": "kv-reversen-2"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `document_key` | yes | PDF path in storage |
| `project_id` | no | Project identifier (default: `""`) |

**Example:**

```bash
curl -X POST http://localhost:8008/classify \
  -H "Content-Type: application/json" \
  -d '{"document_key": "raw/document.pdf", "project_id": "kv-reversen-2"}'
```

**Response:**

```json
{
  "document_key": "raw/document.pdf",
  "category": "drawing",
  "confidence": "high",
  "visual_cues": [
    "architectural layout with room names",
    "scale bar at the bottom",
    "dimension lines"
  ],
  "title": "Floor plan (1:100)",
  "description": "Arkitektonisk ritning med rumslayout.",
  "screenshot_key": "screenshots/document.png",
  "thumbnails": [
    "thumbnails/document/document_page_1.png",
    "thumbnails/document/document_page_2.png"
  ],
  "pages": 2,
  "duration_ms": 15000,
  "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"
}
```

### Health check

```bash
curl http://localhost:8008/health
```
