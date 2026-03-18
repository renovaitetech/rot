# Storage Service

Document storage service built on MinIO (S3-compatible).

**Port:** 8002

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `S3_ENDPOINT_URL` | `http://minio:9000` | MinIO endpoint |
| `S3_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `S3_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `S3_BUCKET_NAME` | `documents` | Bucket name |

## Endpoints

### Upload document

```
POST /documents/upload?prefix=raw
```

Upload a file to S3 with an optional prefix.

**Parameters:**
- `prefix` (query, optional) — folder prefix, e.g. `raw`, `markdown`, `thumbnails`
- `file` (form) — file to upload

**Example:**

```bash
curl -X POST "http://localhost:8002/documents/upload?prefix=raw" \
  -F "file=@document.pdf"
```

**Response:**

```json
{
  "key": "raw/document.pdf",
  "size": 125000,
  "content_type": "application/pdf"
}
```

### List documents

```
GET /documents/?prefix=raw
```

List files in the bucket with optional prefix filter.

**Example:**

```bash
curl "http://localhost:8002/documents/?prefix=raw"
```

**Response:**

```json
{
  "files": [
    "raw/document.pdf",
    "raw/spec.pdf"
  ],
  "count": 2
}
```

### Download document

```
GET /documents/{path}
```

Download a file by its key.

**Example:**

```bash
curl "http://localhost:8002/documents/raw/document.pdf" -o document.pdf
```

### Delete document

```
DELETE /documents/{path}
```

Delete a file by its key.

**Example:**

```bash
curl -X DELETE "http://localhost:8002/documents/raw/document.pdf"
```

**Response:**

```json
{
  "deleted": "raw/document.pdf"
}
```

### Health check

```bash
curl http://localhost:8002/health
```
