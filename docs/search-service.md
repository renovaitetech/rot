# Search Service

Full-text search service built on Elasticsearch with Swedish language support.

**Port:** 8007

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` | Elasticsearch endpoint |
| `DOCUMENTS_INDEX_NAME` | `documents` | Index name for document catalog |
| `CHUNKS_INDEX_NAME` | `chunks` | Index name for text chunks |

## Index architecture

Two indices mirroring the Qdrant structure:

| Index | Purpose |
|-------|---------|
| `documents` | Document catalog — metadata, title, description for finding documents by content |
| `chunks` | Text chunks — full-text search across document text with Swedish analyzer |

### Analyzers

| Analyzer | Description |
|----------|-------------|
| `swedish_custom` | Swedish stemmer + stop words — for Swedish text matching |
| `standard` | Default ES analyzer — for names, emails, phone numbers, URLs |

### `documents` index mapping

| Field | Type | Description |
|-------|------|-------------|
| `filename` | keyword | Original filename |
| `title` | text (swedish) + keyword | Document title |
| `description` | text (swedish) | Short description in Swedish |
| `category` | keyword | `drawing`, `presentation`, `text_spec`, `table_spec` |
| `subtype` | keyword | Visual subtype: `apartment_plan`, `facade`, etc. |
| `screenshot_key` | keyword | Path to screenshot in storage |
| `pages` | integer | Number of pages |
| `status` | keyword | Processing status |
| `source_key` | keyword | Source PDF path in storage |
| `project_id` | keyword | Project identifier |
| `document_id` | keyword | Qdrant document ID |

### `chunks` index mapping

Every text field is indexed with both analyzers (multi-field):

| Field | Type | Sub-fields | Description |
|-------|------|------------|-------------|
| `text` | text (swedish) | `text.standard` | Original Markdown text |
| `text_clean` | text (swedish) | `text_clean.standard` | Clean text without markup |
| `section_title` | text (standard) | `section_title.keyword` | Section heading |
| `source` | keyword | — | Source document key in storage |
| `doc_type` | keyword | — | Text document type: `FU`, `ATA`, `PM`, etc. |
| `category` | keyword | — | Document category |
| `subtype` | keyword | — | Visual subtype |
| `project_id` | keyword | — | Project identifier |
| `document_id` | keyword | — | Link to documents index |
| `token_count` | integer | — | Number of tokens |
| `index` | integer | — | Chunk position in document |

## Endpoints

### Initialize indices

```
POST /index/init
```

Creates both indices with mappings. Optionally recreates them.

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
  "recreated": false,
  "doc_counts": {
    "documents": 42,
    "chunks": 380
  }
}
```

---

### Index documents (catalog)

```
POST /documents
```

Bulk index document catalog entries.

**Request:**

```json
{
  "documents": [
    {
      "filename": "document.pdf",
      "title": "Floor plan (1:100)",
      "description": "Arkitektonisk ritning med rumslayout.",
      "category": "drawing",
      "subtype": "apartment_plan",
      "screenshot_key": "screenshots/document.png",
      "pages": 2,
      "status": "classified",
      "source_key": "raw/document.pdf",
      "project_id": "kv-reversen-2",
      "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"
    }
  ]
}
```

**Response:**

```json
{
  "indexed": 1
}
```

### Search documents (catalog)

```
POST /documents/search
```

Search document catalog by title and description. Use this to find documents by what they describe.

**Request:**

```json
{
  "query": "planlösning lägenhet",
  "limit": 5,
  "category": "drawing",
  "project_id": "kv-reversen-2"
}
```

Only `query` is required. Filters (`limit`, `category`, `subtype`, `project_id`) are optional.

**Response:**

```json
{
  "results": [
    {
      "id": "abc123",
      "score": 8.5,
      "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae",
      "filename": "document.pdf",
      "title": "Floor plan (1:100)",
      "description": "Arkitektonisk ritning med rumslayout.",
      "category": "drawing",
      "subtype": "apartment_plan",
      "screenshot_key": "screenshots/document.png",
      "pages": 2,
      "status": "classified",
      "source_key": "raw/document.pdf",
      "project_id": "kv-reversen-2"
    }
  ],
  "count": 1
}
```

### Delete documents (catalog)

```
DELETE /documents
```

Delete catalog entries by filter. At least one filter is required.

**Examples:**

```bash
# Delete by source key
curl -X DELETE http://localhost:8007/documents \
  -H "Content-Type: application/json" \
  -d '{"source_key": "raw/document.pdf"}'

# Delete by project
curl -X DELETE http://localhost:8007/documents \
  -H "Content-Type: application/json" \
  -d '{"project_id": "kv-reversen-2"}'
```

**Response:**

```json
{
  "deleted": 1,
  "filters": {"source_key": "raw/document.pdf"}
}
```

---

### Index chunks

```
POST /chunks
```

Bulk index text chunks.

**Request:**

```json
{
  "chunks": [
    {
      "text": "## Fasadrenovering\n\nArbetet omfattar...",
      "text_clean": "Fasadrenovering Arbetet omfattar...",
      "token_count": 245,
      "index": 0,
      "source": "markdown/document.md",
      "section_title": "Fasadrenovering",
      "doc_type": "FU",
      "project_id": "kv-reversen-2",
      "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"
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
DOCS=$(echo $CHUNKS | jq '{chunks: [.chunks[] | {
  text, text_clean, token_count, index, source, section_title,
  doc_type: "FU", project_id: "kv-reversen-2",
  document_id: "280b9e92-7823-49d2-bbe6-587c9d722aae"
}]}')

# Index
curl -s -X POST http://localhost:8007/chunks \
  -H "Content-Type: application/json" \
  -d "$DOCS" | jq .
```

**Response:**

```json
{
  "indexed": 9
}
```

### Search chunks

```
POST /chunks/search
```

Full-text search across chunk text using `multi_match` with both Swedish and standard analyzers. Use this to find specific text content within documents.

**Request:**

```json
{
  "query": "fasadrenovering fönsterbyte",
  "limit": 5,
  "doc_type": "FU",
  "project_id": "kv-reversen-2",
  "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"
}
```

Only `query` is required. All filters are optional.

**Examples:**

```bash
# Search by name (uses standard analyzer)
curl -s -X POST http://localhost:8007/chunks/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Shamile Israilov"}' \
  | jq '.results[] | {score, source, section_title, text: .text[:100]}'

# Search in Swedish (uses swedish analyzer with stemming)
curl -s -X POST http://localhost:8007/chunks/search \
  -H "Content-Type: application/json" \
  -d '{"query": "fasadrenovering fönsterbyte"}' \
  | jq '.results[] | {score, source, section_title}'

# Search within specific document
curl -s -X POST http://localhost:8007/chunks/search \
  -H "Content-Type: application/json" \
  -d '{"query": "energibrunnar", "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"}' \
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
      "category": "text_spec",
      "subtype": "",
      "project_id": "kv-reversen-2",
      "document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"
    }
  ],
  "count": 1
}
```

### Delete chunks

```
DELETE /chunks
```

Delete chunks by filter. At least one filter is required.

**Examples:**

```bash
# Delete by source document
curl -X DELETE http://localhost:8007/chunks \
  -H "Content-Type: application/json" \
  -d '{"source": "markdown/document.md"}'

# Delete all chunks for a document
curl -X DELETE http://localhost:8007/chunks \
  -H "Content-Type: application/json" \
  -d '{"document_id": "280b9e92-7823-49d2-bbe6-587c9d722aae"}'

# Delete by project
curl -X DELETE http://localhost:8007/chunks \
  -H "Content-Type: application/json" \
  -d '{"project_id": "kv-reversen-2"}'
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

### chunks/search — full-text across document text

Uses `multi_match` with `best_fields` type and `fuzziness: AUTO`:

| Query type | Example | Matched by |
|------------|---------|------------|
| Person name | `Shamile Israilov` | `text.standard` |
| Email | `shamile@fk-gruppen.se` | `text.standard` |
| Phone number | `08-588 856 13` | `text.standard` |
| Swedish term | `fasadrenovering` | `text` (swedish analyzer with stemming) |
| Swedish phrase | `energibrunnar värmesystem` | `text` (swedish analyzer) |

### documents/search — find documents by description

Searches `title`, `title.keyword`, `description`, `filename`. Best for queries like "floor plan apartment" or "fasadrenovering" when looking for a specific document.

Note: Cross-language queries (e.g. Russian query against Swedish text) are better handled by vector search (Qdrant) rather than keyword search.
