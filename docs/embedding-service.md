# Embedding Service

Text embedding service using Jina Embeddings API with Redis caching.

**Port:** 8005

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `JINA_EMBEDDING_API_KEY` | — | Jina API key |
| `JINA_EMBEDDING_BASE_URL` | `https://api.jina.ai/v1/embeddings` | Jina API endpoint |
| `JINA_EMBEDDING_MODEL` | `jina-embeddings-v4` | Embedding model |
| `EMBEDDING_DIMENSIONS` | `2048` | Vector dimensions |
| `REDIS_URL` | `redis://redis:6379` | Redis connection URL |
| `CACHE_TTL` | `2592000` | Cache TTL in seconds (30 days) |

## Endpoints

### Embed single text

```
POST /embed
```

Embeds a single text. Results are cached in Redis by SHA-256 hash of the input text.

**Request:**

```json
{
  "text": "Krav på fasadrenovering"
}
```

**Example:**

```bash
curl -X POST http://localhost:8005/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "Krav på fasadrenovering"}'
```

**Response:**

```json
{
  "embedding": [0.0234, -0.0156, 0.0412, ...],
  "dimensions": 2048,
  "elapsed_ms": 342.5,
  "cached": false
}
```

Repeated requests with the same text return `cached: true` and `elapsed_ms: 0`.

### Embed batch

```
POST /embed/batch
```

Embeds multiple texts in a single API call. No caching.

**Request:**

```json
{
  "texts": [
    "Fasadrenovering och fönsterbyte",
    "Energibrunnar och värmesystem",
    "VVS-installation"
  ]
}
```

**Example:**

```bash
curl -X POST http://localhost:8005/embed/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Hello world", "Привет мир", "Hej världen"]}'
```

**Response:**

```json
{
  "embeddings": [
    [0.0234, -0.0156, ...],
    [0.0189, -0.0201, ...],
    [0.0267, -0.0134, ...]
  ],
  "dimensions": 2048,
  "count": 3,
  "elapsed_ms": 521.3
}
```

### Health check

```bash
curl http://localhost:8005/health
```
