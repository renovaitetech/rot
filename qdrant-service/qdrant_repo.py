import logging
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from config import settings

logger = logging.getLogger(__name__)

client: QdrantClient = None


def init_client():
    global client
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    logger.info(f"Connected to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")


def _ensure_collection(name: str):
    """Create collection if not exists."""
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.DOT,
            ),
        )
        logger.info(f"Created collection '{name}' (dim={settings.embedding_dimensions}, metric=Dot)")
    else:
        logger.info(f"Collection '{name}' already exists")


def init_collections(recreate: bool = False):
    """Create both collections if not exist. Optionally recreate."""
    for name in (settings.documents_collection, settings.chunks_collection):
        if recreate:
            client.delete_collection(name)
            logger.info(f"Deleted collection '{name}'")
        _ensure_collection(name)

    return {
        "documents": client.get_collection(settings.documents_collection),
        "chunks": client.get_collection(settings.chunks_collection),
    }


# ============================================================================
# Documents collection (catalog)
# ============================================================================


def upsert_document(embedding: list[float], payload: dict) -> str:
    """Upsert a document into the catalog. Returns document_id."""
    doc_id = str(uuid.uuid4())
    client.upsert(
        collection_name=settings.documents_collection,
        points=[
            PointStruct(id=doc_id, vector=embedding, payload=payload),
        ],
    )
    logger.info(f"Upserted document '{doc_id}' into catalog")
    return doc_id


def get_document(doc_id: str) -> dict | None:
    """Get a document by ID from the catalog."""
    results = client.retrieve(
        collection_name=settings.documents_collection,
        ids=[doc_id],
        with_payload=True,
        with_vectors=False,
    )
    if not results:
        return None
    point = results[0]
    return {"id": str(point.id), "payload": point.payload}


def search_documents(
    vector: list[float],
    limit: int = 5,
    filters: dict | None = None,
) -> list[dict]:
    """Semantic search over document catalog."""
    query_filter = _build_filter(filters)
    results = client.query_points(
        collection_name=settings.documents_collection,
        query=vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )
    return [
        {"id": str(p.id), "score": p.score, "payload": p.payload}
        for p in results.points
    ]


def delete_document(doc_id: str) -> None:
    """Delete a document from catalog by ID."""
    client.delete(
        collection_name=settings.documents_collection,
        points_selector=[doc_id],
    )
    logger.info(f"Deleted document '{doc_id}' from catalog")


# ============================================================================
# Chunks collection (RAG)
# ============================================================================


def upsert_chunks(points: list[dict]) -> int:
    """Upsert chunk points into chunks collection.
    Each point: {embedding: [...], payload: {...}}
    """
    structs = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=p["embedding"],
            payload=p["payload"],
        )
        for p in points
    ]
    client.upsert(
        collection_name=settings.chunks_collection,
        points=structs,
    )
    logger.info(f"Upserted {len(structs)} chunks")
    return len(structs)


def search_chunks(
    vector: list[float],
    limit: int = 5,
    filters: dict | None = None,
) -> list[dict]:
    """Search for similar chunks."""
    query_filter = _build_filter(filters)
    results = client.query_points(
        collection_name=settings.chunks_collection,
        query=vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )
    return [
        {"id": str(p.id), "score": p.score, "payload": p.payload}
        for p in results.points
    ]


def delete_chunks_by_filter(filters: dict) -> None:
    """Delete chunks matching filter conditions."""
    conditions = [
        FieldCondition(key=k, match=MatchValue(value=v))
        for k, v in filters.items()
        if v is not None
    ]
    if not conditions:
        raise ValueError("At least one filter is required for deletion")

    client.delete(
        collection_name=settings.chunks_collection,
        points_selector=Filter(must=conditions),
    )
    logger.info(f"Deleted chunks matching {filters}")


# ============================================================================
# Helpers
# ============================================================================


def _build_filter(filters: dict | None) -> Filter | None:
    if not filters:
        return None
    conditions = [
        FieldCondition(key=k, match=MatchValue(value=v))
        for k, v in filters.items()
        if v is not None
    ]
    return Filter(must=conditions) if conditions else None


# ============================================================================
# Migration
# ============================================================================


def migrate_to_two_collections() -> dict:
    """Migrate data from old single 'documents' collection to documents + chunks.

    Reads all points from 'documents' (old chunks), groups by source,
    recreates 'documents' as clean catalog, moves chunks to 'chunks' with document_id.
    """
    old_collection = settings.documents_collection
    stats = {"documents_created": 0, "chunks_migrated": 0}

    # Scroll all points from the old collection
    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=old_collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points, next_offset = result
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    if not all_points:
        logger.info("No points to migrate")
        return stats

    # Filter out catalog entries (already migrated) — they have 'source_key' instead of 'source'
    chunk_points = [p for p in all_points if "source" in p.payload and "source_key" not in p.payload]
    if not chunk_points:
        logger.info("No chunk points to migrate (only catalog entries found)")
        return stats

    # Group by source
    by_source: dict[str, list] = {}
    for point in chunk_points:
        source = point.payload.get("source", "unknown")
        by_source.setdefault(source, []).append(point)

    # Ensure chunks collection exists
    _ensure_collection(settings.chunks_collection)

    # Collect catalog entries to insert
    catalog_entries = []

    for source, points in by_source.items():
        doc_id = str(uuid.uuid4())
        doc_payload = {
            "source_key": source,
            "document_type": points[0].payload.get("doc_type", "unknown"),
            "project_id": points[0].payload.get("project_id", ""),
            "status": "indexed",
            "pages": 0,
        }
        catalog_entries.append(
            PointStruct(
                id=doc_id,
                vector=[0.0] * settings.embedding_dimensions,
                payload=doc_payload,
            )
        )
        stats["documents_created"] += 1

        # Move chunks to chunks collection with document_id
        chunk_structs = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=point.vector,
                payload={**point.payload, "document_id": doc_id},
            )
            for point in points
        ]
        client.upsert(
            collection_name=settings.chunks_collection,
            points=chunk_structs,
        )
        stats["chunks_migrated"] += len(chunk_structs)

    # Recreate documents collection as clean catalog
    client.delete_collection(old_collection)
    client.create_collection(
        collection_name=old_collection,
        vectors_config=VectorParams(
            size=settings.embedding_dimensions,
            distance=Distance.DOT,
        ),
    )
    logger.info(f"Recreated '{old_collection}' as clean catalog")

    # Insert catalog entries
    if catalog_entries:
        client.upsert(
            collection_name=old_collection,
            points=catalog_entries,
        )

    logger.info(f"Migration complete: {stats}")
    return stats
