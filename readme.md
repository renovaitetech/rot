# rot

AI-powered platform by Renovaite for renovation project management. Assists with tender documentation processing, project tracking, and LLM+RAG knowledge base for ROT (Reconstruction, Overhaul, Technical maintenance) projects.

## Architecture

```
                         ┌─────────────────┐
                         │   open-webui    │ :3000
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │  proxy-service  │ :8000
                         └────────┬────────┘
                                  │
                         ┌────────▼────────┐
                         │   mcp-server    │ :8001
                         └────────┬────────┘
                           ┌──────┴──────┐
                           ▼             ▼
                  embedding-service   qdrant-service
                      :8005               :8006

──── Document processing pipeline ────────────────────────

  MinIO (raw PDF)
       │
       ▼
  classifier-service :8008
  (vision model, first page)
       │
       ├─ drawing / presentation ──► vision-service :8009
       │                             (page-by-page analysis)
       │
       └─ text_spec / table_spec ──► parser-service :8003
                                     (PDF → Markdown)
                                          │
                                          ▼
                                     chunking-service :8004
                                     (semantic chunks)
                                          │
                                    ┌─────┴─────┐
                                    ▼           ▼
                             qdrant-service  search-service
                             (vector store)  (full-text)
                                :8006           :8007
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| `open-webui` | 3000 | Chat UI |
| `proxy-service` | 8000 | OpenAI-compatible proxy, routes LLM requests |
| `mcp-server` | 8001 | MCP server for RAG tools |
| `storage-service` | 8002 | File storage wrapper over MinIO |
| `parser-service` | 8003 | PDF → Markdown conversion |
| `chunking-service` | 8004 | Semantic chunking with DeepSeek or recursive |
| `embedding-service` | 8005 | Text → vector (Jina, 2048-dim) with Redis cache |
| `qdrant-service` | 8006 | Vector search over Qdrant |
| `search-service` | 8007 | Full-text search over Elasticsearch |
| `classifier-service` | 8008 | Document classification via vision model |
| `vision-service` | 8009 | Visual analysis of drawings and presentations |
| `minio` | 9000/9001 | Object storage |
| `qdrant` | 6333/6334 | Vector database |
| `elasticsearch` | 9200 | Full-text search engine |
| `redis` | 6379 | Cache for embeddings |

## Storage structure

### MinIO — `documents` bucket

| Prefix | Content |
|--------|---------|
| `raw/` | Original PDF files |
| `markdown/` | Parsed Markdown from parser-service |
| `screenshots/` | First-page screenshots (2K PNG) from classifier-service |
| `thumbnails/{filename}/` | Per-page thumbnails from classifier-service |

### Qdrant — two collections

| Collection | Description |
|------------|-------------|
| `documents` | Document catalog — one point per document, vector of `title + description` |
| `chunks` | Text chunks for RAG — multiple points per document, vector of chunk text |

### Elasticsearch — two indices

| Index | Description |
|-------|-------------|
| `documents` | Document catalog for keyword search on title/description |
| `chunks` | Text chunks for full-text search with Swedish analyzer |

Both Qdrant collections and both ES indices mirror the same two-level structure: document metadata catalog + text chunks.

## Document processing pipeline

### 1. Upload
```bash
curl -X POST "http://localhost:8002/documents/upload?prefix=raw" -F "file=@document.pdf"
```

### 2. Classify
Renders first page as a 2K screenshot, classifies document type via vision model, registers in Qdrant and ES catalog.
```bash
curl -X POST http://localhost:8008/classify \
  -H "Content-Type: application/json" \
  -d '{"document_key": "raw/document.pdf", "project_id": "kv-reversen-2"}'
```

### 3a. Analyze drawings and presentations (vision)
```bash
# Drawing
curl -X POST http://localhost:8009/analyze/drawing \
  -H "Content-Type: application/json" \
  -d '{"document_key": "raw/drawing.pdf"}'

# Presentation
curl -X POST http://localhost:8009/analyze/presentation \
  -H "Content-Type: application/json" \
  -d '{"document_key": "raw/presentation.pdf"}'
```

### 3b. Parse and chunk text documents
```bash
# Parse PDF → Markdown
curl -X POST http://localhost:8003/parse \
  -H "Content-Type: application/json" \
  -d '{"key": "raw/document.pdf"}'

# Chunk Markdown
curl -X POST http://localhost:8004/chunk \
  -H "Content-Type: application/json" \
  -d '{"key": "markdown/document.md"}'
```

### 4. Index chunks (vector + full-text)
```bash
# Embed and store in Qdrant
curl -X POST http://localhost:8006/points \
  -H "Content-Type: application/json" \
  -d '{"points": [{"embedding": [...], "payload": {"text": "...", "document_id": "..."}}]}'

# Index in Elasticsearch
curl -X POST http://localhost:8007/chunks \
  -H "Content-Type: application/json" \
  -d '{"chunks": [{"text": "...", "text_clean": "...", "document_id": "..."}]}'
```

## Inference providers

Classifier and vision services support two inference providers:

| Provider | Variable | Default model |
|----------|----------|---------------|
| `ollama` | `OLLAMA_URL`, `OLLAMA_MODEL` | `qwen3.5:9b` |
| `openrouter` | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | classifier: `qwen/qwen3.5-9b`, vision: `qwen/qwen3.5-122b-a10b` |

Switch provider via env: `INFERENCE_PROVIDER=openrouter` (classifier) / `VISION_PROVIDER=openrouter` (vision).

## Running

```bash
# Copy and fill in env
cp .env.example .env

# Start all services
docker compose up -d

# Rebuild a specific service
docker compose up --build classifier-service -d
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `MINIO_ROOT_USER` | MinIO access key |
| `MINIO_ROOT_PASSWORD` | MinIO secret key |
| `DEEPSEEK_API_KEY` | DeepSeek API key (chunking-service, proxy-service) |
| `DEEPSEEK_API_URL` | DeepSeek API URL |
| `JINA_EMBEDDING_API_KEY` | Jina embedding API key |
| `JINA_EMBEDDING_BASE_URL` | Jina embedding API base URL |
| `JINA_EMBEDDING_MODEL` | Jina embedding model name |
| `OPENROUTER_API_KEY` | OpenRouter API key (classifier, vision) |
| `OPENROUTER_MODEL` | OpenRouter model ID |
| `INFERENCE_PROVIDER` | Classifier inference: `ollama` \| `openrouter` (default: `ollama`) |
| `VISION_PROVIDER` | Vision inference: `ollama` \| `openrouter` (default: `ollama`) |
| `OLLAMA_URL` | Ollama server URL |
| `OLLAMA_MODEL` | Ollama model name |

## Documentation

- [Storage Service](docs/storage-service.md)
- [Parser Service](docs/parser-service.md)
- [Chunking Service](docs/chunking-service.md)
- [Embedding Service](docs/embedding-service.md)
- [Classifier Service](docs/classifier-service.md)
- [Vision Service](docs/vision-service.md)
- [Qdrant Service](docs/qdrant-service.md)
- [Search Service](docs/search-service.md)
