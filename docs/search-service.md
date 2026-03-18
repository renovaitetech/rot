# Search Service

Full-text search service built on Elasticsearch with Swedish language support.

**Port:** 8007

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` | Elasticsearch endpoint |
| `INDEX_NAME` | `documents` | Index name |

## Index schema

### Analyzers

| Analyzer | Description |
|----------|-------------|
| `swedish_custom` | Swedish stemmer + stop words — for Swedish text matching |
| `standard` | Default ES analyzer — for names, emails, phone numbers, URLs |

### Field mapping

Every text field is indexed with both analyzers (multi-field):

| Field | Type | Sub-fields | Description |
|-------|------|------------|-------------|
| `text` | text (swedish) | `text.standard` | Original Markdown text |
| `text_clean` | text (swedish) | `text_clean.standard` | Clean text without markup |
| `section_title` | text (standard) | `section_title.keyword` | Section heading |
| `source` | keyword | — | Source document key in storage |
| `doc_type` | keyword | — | Document type, e.g. `FU` |
| `project_id` | keyword | — | Project identifier |
| `token_count` | integer | — | Number of tokens |
| `index` | integer | — | Chunk position in document |

## Endpoints

### Initialize index

```
POST /index/init
```

Creates the index with mapping. Optionally recreates it.

**Example:**

```bash
# Create if not exists
curl -X POST http://localhost:8007/index/init \
  -H "Content-Type: application/json" \
  -d '{}'

# Recreate (delete + create)
curl -X POST http://localhost:8007/index/init \
  -H "Content-Type: application/json" \
  -d '{"recreate": true}'
```

**Response:**

```json
{
  "index": "documents",
  "recreated": false,
  "doc_count": 142
}
```

### Index documents

```
POST /documents
```

Bulk index document chunks.

**Request:**

```json
{
  "documents": [
    {
      "text": "## Fasadrenovering\n\nArbetet omfattar...",
      "text_clean": "Fasadrenovering Arbetet omfattar...",
      "token_count": 245,
      "index": 0,
      "source": "markdown/document.md",
      "section_title": "Fasadrenovering",
      "doc_type": "FU",
      "project_id": "proj1"
    }
  ]
}
```

**Example — index chunks from chunking-service:**

```bash
# Get chunks
CHUNKS=$(curl -s -X POST http://localhost:8004/chunk \
  -H "Content-Type: application/json" \
  -d '{"key": "markdown/document.md"}')

# Format for search-service
DOCS=$(echo $CHUNKS | jq '{documents: [.chunks[] | {
  text, text_clean, token_count, index, source, section_title,
  doc_type: "FU", project_id: "proj1"
}]}')

# Index
curl -s -X POST http://localhost:8007/documents \
  -H "Content-Type: application/json" \
  -d "$DOCS" | jq .
```

**Response:**

```json
{
  "indexed": 9
}
```

### Search

```
POST /search
```

Full-text search using `multi_match` across text fields with both Swedish and standard analyzers. Supports fuzzy matching.

**Request:**

```json
{
  "query": "Shamile Israilov",
  "limit": 5,
  "doc_type": "FU",
  "project_id": "proj1"
}
```

Only `query` is required. `limit`, `doc_type`, `project_id` are optional.

**Examples:**

```bash
# Search by name (uses standard analyzer)
curl -s -X POST http://localhost:8007/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Shamile Israilov"}' \
  | jq '.results[] | {score, source, section_title, text: .text[:100]}'

# Search in Swedish (uses swedish analyzer with stemming)
curl -s -X POST http://localhost:8007/search \
  -H "Content-Type: application/json" \
  -d '{"query": "fasadrenovering fönsterbyte"}' \
  | jq '.results[] | {score, source, section_title}'

# Search with filters
curl -s -X POST http://localhost:8007/search \
  -H "Content-Type: application/json" \
  -d '{"query": "energibrunnar", "doc_type": "FU", "project_id": "proj1"}' \
  | jq .
```

**Response:**

```json
{
  "results": [
    {
      "id": "abc123",
      "score": 12.45,
      "text": "FK-Gruppen Tel: 08-588 856 13 Shamile Israilov shamile@fk-gruppen.se",
      "source": "markdown/kv_reversen_2_pm01.md",
      "section_title": "Ändringar avseende fasad",
      "doc_type": "FU",
      "project_id": "proj1"
    }
  ],
  "count": 1
}
```

### Delete documents

```
DELETE /documents
```

Delete documents matching filter conditions. At least one filter is required.

**Examples:**

```bash
# Delete by source document
curl -X DELETE http://localhost:8007/documents \
  -H "Content-Type: application/json" \
  -d '{"source": "markdown/document.md"}'

# Delete by project
curl -X DELETE http://localhost:8007/documents \
  -H "Content-Type: application/json" \
  -d '{"project_id": "proj1"}'

# Delete by doc_type
curl -X DELETE http://localhost:8007/documents \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "FU"}'
```

**Response:**

```json
{
  "deleted": 9,
  "filters": {"source": "markdown/document.md"}
}
```

### Health check

```bash
curl http://localhost:8007/health
```

## Search behavior

The search uses `multi_match` with `best_fields` type and `fuzziness: AUTO`:

| Query type | Example | Matched by |
|------------|---------|------------|
| Person name | `Shamile Israilov` | `text.standard` |
| Email | `shamile@fk-gruppen.se` | `text.standard` |
| Phone number | `08-588 856 13` | `text.standard` |
| Swedish term | `fasadrenovering` | `text` (swedish analyzer with stemming) |
| Swedish phrase | `energibrunnar värmesystem` | `text` (swedish analyzer) |

Note: Cross-language queries (e.g. Russian query against Swedish text) are better handled by vector search (Qdrant) rather than keyword search.
