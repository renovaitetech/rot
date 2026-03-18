# Qdrant Service

Vector storage and search service. Wraps Qdrant for storing document chunks with embeddings.

**Port:** 8006

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `qdrant` | Qdrant server host |
| `QDRANT_PORT` | `6333` | Qdrant server port |
| `COLLECTION_NAME` | `documents` | Collection name |
| `EMBEDDING_DIMENSIONS` | `2048` | Vector dimensions |

## Collection schema

- **Metric:** Dot Product (embeddings are L2 normalized)
- **Dimensions:** 2048

### Point payload fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Original Markdown text (for display) |
| `text_clean` | string | Clean text without markup (for reference) |
| `token_count` | int | Number of tokens |
| `index` | int | Chunk position in document |
| `source` | string | Source document key in storage |
| `section_title` | string | Section heading |
| `doc_type` | string | Document type, e.g. `FU` |
| `project_id` | string | Project identifier |

## Endpoints

### Initialize collection

```
POST /collections/init
```

Creates the collection if it doesn't exist. Optionally recreates it.

**Example:**

```bash
# Create if not exists
curl -X POST http://localhost:8006/collections/init \
  -H "Content-Type: application/json" \
  -d '{}'

# Recreate (delete + create)
curl -X POST http://localhost:8006/collections/init \
  -H "Content-Type: application/json" \
  -d '{"recreate": true}'
```

**Response:**

```json
{
  "collection": "documents",
  "recreated": false,
  "points_count": 142,
  "vectors_count": 142
}
```

### Upsert points

```
POST /points
```

Store document chunks with their embeddings.

**Request:**

```json
{
  "points": [
    {
      "embedding": [0.0234, -0.0156, ...],
      "payload": {
        "text": "## Fasadrenovering\n\nArbetet omfattar...",
        "text_clean": "Fasadrenovering Arbetet omfattar...",
        "token_count": 245,
        "index": 0,
        "source": "markdown/document.md",
        "section_title": "Fasadrenovering",
        "doc_type": "FU",
        "project_id": "proj1"
      }
    }
  ]
}
```

**Example:**

```bash
curl -X POST http://localhost:8006/points \
  -H "Content-Type: application/json" \
  -d '{"points": [{"embedding": [0.1, 0.2, ...], "payload": {"text": "test", "text_clean": "test", "token_count": 1, "index": 0, "source": "test.md", "section_title": "Test", "doc_type": "FU", "project_id": "proj1"}}]}'
```

**Response:**

```json
{
  "upserted": 1
}
```

### Search

```
POST /search
```

Semantic similarity search with optional filters.

**Request:**

```json
{
  "vector": [0.0234, -0.0156, ...],
  "limit": 5,
  "doc_type": "FU",
  "project_id": "proj1"
}
```

**Example:**

```bash
# Get embedding for query
VECTOR=$(curl -s -X POST http://localhost:8005/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "krav på hissar"}' | jq '.embedding')

# Search in Qdrant
curl -s -X POST http://localhost:8006/search \
  -H "Content-Type: application/json" \
  -d "{\"vector\": $VECTOR, \"limit\": 3}"
```

**Response:**

```json
{
  "results": [
    {
      "id": "a1b2c3d4-...",
      "score": 0.7823,
      "payload": {
        "text": "## Hissar\n\nKrav på nya hissar...",
        "text_clean": "Hissar Krav på nya hissar...",
        "source": "markdown/fu_hissar.md",
        "section_title": "Hissar",
        "doc_type": "FU",
        "project_id": "proj1"
      }
    }
  ],
  "count": 1
}
```

### Search with filters

```bash
# Filter by doc_type
curl -s -X POST http://localhost:8006/search \
  -H "Content-Type: application/json" \
  -d "{\"vector\": $VECTOR, \"limit\": 5, \"doc_type\": \"FU\"}"

# Filter by project_id
curl -s -X POST http://localhost:8006/search \
  -H "Content-Type: application/json" \
  -d "{\"vector\": $VECTOR, \"limit\": 5, \"project_id\": \"proj1\"}"
```

### Delete points

```
DELETE /points
```

Delete points matching filter conditions. At least one filter is required.

**Example:**

```bash
# Delete all points for a specific document
curl -X DELETE http://localhost:8006/points \
  -H "Content-Type: application/json" \
  -d '{"source": "markdown/document.md"}'

# Delete all points for a project
curl -X DELETE http://localhost:8006/points \
  -H "Content-Type: application/json" \
  -d '{"project_id": "proj1"}'

# Delete by doc_type
curl -X DELETE http://localhost:8006/points \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "FU"}'
```

**Response:**

```json
{
  "deleted": true,
  "filters": {"source": "markdown/document.md"}
}
```

### Health check

```bash
curl http://localhost:8006/health
```
