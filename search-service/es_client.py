import logging
from elasticsearch import AsyncElasticsearch

from config import settings

logger = logging.getLogger(__name__)

es: AsyncElasticsearch = None

DOCUMENTS_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "swedish_custom": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "swedish_stop", "swedish_stemmer"],
                },
            },
            "filter": {
                "swedish_stop": {
                    "type": "stop",
                    "stopwords": "_swedish_",
                },
                "swedish_stemmer": {
                    "type": "stemmer",
                    "language": "swedish",
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "filename": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "swedish_custom",
                "fields": {
                    "keyword": {"type": "keyword"},
                },
            },
            "description": {
                "type": "text",
                "analyzer": "swedish_custom",
            },
            "category": {"type": "keyword"},
            "subtype": {"type": "keyword"},
            "screenshot_key": {"type": "keyword"},
            "pages": {"type": "integer"},
            "status": {"type": "keyword"},
            "source_key": {"type": "keyword"},
            "project_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
        },
    },
}

CHUNKS_INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "swedish_custom": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "swedish_stop", "swedish_stemmer"],
                },
            },
            "filter": {
                "swedish_stop": {
                    "type": "stop",
                    "stopwords": "_swedish_",
                },
                "swedish_stemmer": {
                    "type": "stemmer",
                    "language": "swedish",
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "text": {
                "type": "text",
                "analyzer": "swedish_custom",
                "fields": {
                    "standard": {
                        "type": "text",
                        "analyzer": "standard",
                    },
                },
            },
            "text_clean": {
                "type": "text",
                "analyzer": "swedish_custom",
                "fields": {
                    "standard": {
                        "type": "text",
                        "analyzer": "standard",
                    },
                },
            },
            "source": {"type": "keyword"},
            "section_title": {
                "type": "text",
                "fields": {
                    "keyword": {"type": "keyword"},
                },
            },
            "doc_type": {"type": "keyword"},
            "category": {"type": "keyword"},
            "subtype": {"type": "keyword"},
            "project_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "token_count": {"type": "integer"},
            "index": {"type": "integer"},
        },
    },
}


async def init_es():
    global es
    es = AsyncElasticsearch(settings.elasticsearch_url)
    logger.info(f"Connected to Elasticsearch at {settings.elasticsearch_url}")


async def close_es():
    if es:
        await es.close()


async def init_indices(recreate: bool = False):
    """Create both indices with mappings. Optionally recreate."""
    counts = {}
    for name, mapping in [
        (settings.documents_index_name, DOCUMENTS_INDEX_MAPPING),
        (settings.chunks_index_name, CHUNKS_INDEX_MAPPING),
    ]:
        if recreate and await es.indices.exists(index=name):
            await es.indices.delete(index=name)
            logger.info(f"Deleted index '{name}'")

        if not await es.indices.exists(index=name):
            await es.indices.create(index=name, body=mapping)
            logger.info(f"Created index '{name}'")
        else:
            logger.info(f"Index '{name}' already exists")

        stats = await es.indices.stats(index=name)
        counts[name] = stats["indices"][name]["primaries"]["docs"]["count"]

    return counts


# --- Documents index ---

async def index_documents(docs: list[dict]) -> int:
    """Bulk index document catalog entries."""
    if not docs:
        return 0

    operations = []
    for doc in docs:
        operations.append({"index": {"_index": settings.documents_index_name}})
        operations.append(doc)

    result = await es.bulk(operations=operations, refresh=True)

    if result.get("errors"):
        errors = [
            item["index"]["error"]
            for item in result["items"]
            if "error" in item.get("index", {})
        ]
        logger.error(f"Bulk indexing errors: {errors[:3]}")

    indexed = sum(
        1 for item in result["items"]
        if item.get("index", {}).get("result") in ("created", "updated")
    )
    logger.info(f"Indexed {indexed}/{len(docs)} documents")
    return indexed


async def search_documents(
    query: str,
    limit: int = 5,
    category: str | None = None,
    subtype: str | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """Search document catalog by title and description."""
    must = [
        {
            "multi_match": {
                "query": query,
                "fields": [
                    "title^3",
                    "title.keyword^2",
                    "description^2",
                    "filename",
                ],
                "type": "best_fields",
                "fuzziness": "AUTO",
            },
        },
    ]

    filters = []
    if category:
        filters.append({"term": {"category": category}})
    if subtype:
        filters.append({"term": {"subtype": subtype}})
    if project_id:
        filters.append({"term": {"project_id": project_id}})

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filters,
            },
        },
        "size": limit,
    }

    result = await es.search(index=settings.documents_index_name, body=body)

    return [
        {
            "id": hit["_id"],
            "score": hit["_score"],
            "document_id": hit["_source"].get("document_id", ""),
            "filename": hit["_source"].get("filename", ""),
            "title": hit["_source"].get("title", ""),
            "description": hit["_source"].get("description", ""),
            "category": hit["_source"].get("category", ""),
            "subtype": hit["_source"].get("subtype", ""),
            "screenshot_key": hit["_source"].get("screenshot_key", ""),
            "pages": hit["_source"].get("pages", 0),
            "status": hit["_source"].get("status", ""),
            "source_key": hit["_source"].get("source_key", ""),
            "project_id": hit["_source"].get("project_id", ""),
        }
        for hit in result["hits"]["hits"]
    ]


async def delete_documents(filters: dict) -> int:
    """Delete documents from catalog matching filter conditions."""
    must = [{"term": {k: v}} for k, v in filters.items() if v is not None]

    if not must:
        raise ValueError("At least one filter is required")

    result = await es.delete_by_query(
        index=settings.documents_index_name,
        body={"query": {"bool": {"must": must}}},
        refresh=True,
    )

    deleted = result.get("deleted", 0)
    logger.info(f"Deleted {deleted} documents matching {filters}")
    return deleted


# --- Chunks index ---

async def index_chunks(chunks: list[dict]) -> int:
    """Bulk index text chunks."""
    if not chunks:
        return 0

    operations = []
    for chunk in chunks:
        operations.append({"index": {"_index": settings.chunks_index_name}})
        operations.append(chunk)

    result = await es.bulk(operations=operations, refresh=True)

    if result.get("errors"):
        errors = [
            item["index"]["error"]
            for item in result["items"]
            if "error" in item.get("index", {})
        ]
        logger.error(f"Bulk indexing errors: {errors[:3]}")

    indexed = sum(
        1 for item in result["items"]
        if item.get("index", {}).get("result") in ("created", "updated")
    )
    logger.info(f"Indexed {indexed}/{len(chunks)} chunks")
    return indexed


async def search_chunks(
    query: str,
    limit: int = 5,
    doc_type: str | None = None,
    category: str | None = None,
    subtype: str | None = None,
    project_id: str | None = None,
    document_id: str | None = None,
) -> list[dict]:
    """Full-text search across chunk text fields using multi_match."""
    must = [
        {
            "multi_match": {
                "query": query,
                "fields": [
                    "text^2",
                    "text.standard^3",
                    "text_clean",
                    "text_clean.standard^2",
                    "section_title^2",
                    "section_title.standard^3",
                ],
                "type": "best_fields",
                "fuzziness": "AUTO",
            },
        },
    ]

    filters = []
    if doc_type:
        filters.append({"term": {"doc_type": doc_type}})
    if category:
        filters.append({"term": {"category": category}})
    if subtype:
        filters.append({"term": {"subtype": subtype}})
    if project_id:
        filters.append({"term": {"project_id": project_id}})
    if document_id:
        filters.append({"term": {"document_id": document_id}})

    body = {
        "query": {
            "bool": {
                "must": must,
                "filter": filters,
            },
        },
        "size": limit,
    }

    result = await es.search(index=settings.chunks_index_name, body=body)

    return [
        {
            "id": hit["_id"],
            "score": hit["_score"],
            "source": hit["_source"].get("source", ""),
            "text": hit["_source"].get("text", ""),
            "section_title": hit["_source"].get("section_title", ""),
            "doc_type": hit["_source"].get("doc_type", ""),
            "category": hit["_source"].get("category", ""),
            "subtype": hit["_source"].get("subtype", ""),
            "project_id": hit["_source"].get("project_id", ""),
            "document_id": hit["_source"].get("document_id", ""),
        }
        for hit in result["hits"]["hits"]
    ]


async def delete_chunks(filters: dict) -> int:
    """Delete chunks matching filter conditions."""
    must = [{"term": {k: v}} for k, v in filters.items() if v is not None]

    if not must:
        raise ValueError("At least one filter is required")

    result = await es.delete_by_query(
        index=settings.chunks_index_name,
        body={"query": {"bool": {"must": must}}},
        refresh=True,
    )

    deleted = result.get("deleted", 0)
    logger.info(f"Deleted {deleted} chunks matching {filters}")
    return deleted
