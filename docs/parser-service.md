# Parser Service

PDF parsing service. Converts PDF to Markdown and generates page thumbnails.

**Port:** 8003

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_SERVICE_URL` | `http://storage-service:8002` | Storage service URL |

## Endpoints

### Parse PDF

```
POST /parse
```

Downloads PDF from storage, extracts Markdown text and generates PNG thumbnails for each page. Results are uploaded back to storage.

- Markdown is saved to `markdown/{filename}.md`
- Thumbnails are saved to `thumbnails/{filename}/page_{N}.png`
- Page breaks are marked as `<!-- Page N -->` comments in Markdown

**Request:**

```json
{
  "key": "raw/document.pdf"
}
```

**Example:**

```bash
curl -X POST http://localhost:8003/parse \
  -H "Content-Type: application/json" \
  -d '{"key": "raw/document.pdf"}'
```

**Response:**

```json
{
  "markdown_key": "markdown/document.md",
  "thumbnails": [
    "thumbnails/document/page_1.png",
    "thumbnails/document/page_2.png",
    "thumbnails/document/page_3.png"
  ],
  "pages": 3
}
```

### Health check

```bash
curl http://localhost:8003/health
```
