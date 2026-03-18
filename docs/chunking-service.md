# Chunking Service

Document chunking service with two strategies: agentic (DeepSeek LLM) and recursive.

**Port:** 8004

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_SERVICE_URL` | `http://storage-service:8002` | Storage service URL |
| `DEEPSEEK_API_KEY` | — | DeepSeek API key |
| `DEEPSEEK_API_URL` | `https://api.deepseek.com` | DeepSeek API endpoint |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek model name |
| `CHUNK_SIZE` | `512` | Target chunk size in tokens |
| `DEFAULT_STRATEGY` | `agentic` | Default chunking strategy |

## Strategies

| Strategy | Description |
|----------|-------------|
| `agentic` | Sends numbered lines to DeepSeek, receives line ranges for semantic chunking. Best quality, uses API tokens. |
| `recursive` | Fallback using chonkie RecursiveChunker. No API calls, faster but lower quality. |

## Endpoints

### Chunk document

```
POST /chunk
```

Downloads Markdown from storage and splits it into semantic chunks.

Each chunk includes:
- `text` — original Markdown text (for display)
- `text_clean` — stripped text without Markdown/HTML markup (for embeddings)
- `token_count` — number of tokens in the chunk
- `index` — chunk position
- `source` — source document key
- `section_title` — detected section heading

**Request:**

```json
{
  "key": "markdown/document.md",
  "strategy": "agentic"
}
```

**Example:**

```bash
curl -X POST http://localhost:8004/chunk \
  -H "Content-Type: application/json" \
  -d '{"key": "markdown/document.md"}'
```

**Response:**

```json
{
  "source": "markdown/document.md",
  "strategy": "agentic",
  "chunks": [
    {
      "text": "## Fasadrenovering\n\nArbetet omfattar...",
      "text_clean": "Fasadrenovering Arbetet omfattar...",
      "token_count": 245,
      "index": 0,
      "source": "markdown/document.md",
      "section_title": "Fasadrenovering"
    }
  ],
  "total_chunks": 9
}
```

### Chunk with recursive strategy

```bash
curl -X POST http://localhost:8004/chunk \
  -H "Content-Type: application/json" \
  -d '{"key": "markdown/document.md", "strategy": "recursive"}'
```

### Health check

```bash
curl http://localhost:8004/health
```
